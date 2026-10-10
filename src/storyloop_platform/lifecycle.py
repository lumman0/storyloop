"""Own application operations until their coroutines and executor calls settle."""

from __future__ import annotations

import asyncio
import contextvars
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")
GRACE_TIMEOUT = 30
CANCEL_TIMEOUT = 5
logger = logging.getLogger(__name__)


class ServiceStopping(RuntimeError):
    """The application refused admission before invoking the operation."""


class ShutdownTimeout(RuntimeError):
    """Work still borrows application resources after both deadlines."""


async def finish_on_cancel(future: asyncio.Future[T]) -> T:
    """Defer even repeated cancellation until actual completion; never cancel future."""
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
        except BaseException:
            break
    if cancelled:
        if not future.cancelled() and future.exception() is not None:
            error = future.exception()
            logger.error("work failed while cancellation was deferred", exc_info=error)
        raise asyncio.CancelledError
    return future.result()


class OperationSupervisor:
    def __init__(self) -> None:
        self._accepting = True
        self._closed = False
        self._tasks: set[asyncio.Task] = set()
        self._threads: dict[asyncio.Future, str] = {}
        self._service_errors: list[BaseException] = []
        self._shutdown_task: asyncio.Task[None] | None = None

    @property
    def accepting(self) -> bool:
        return self._accepting

    def start(self, operation: Callable[[], Awaitable[T]], *, name: str,
              service: bool = False) -> asyncio.Task[T]:
        if not self.accepting:
            raise ServiceStopping("service is stopping")

        async def invoke() -> T:
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except BaseException as error:
                # Drain can observe a done task before its callback executes.
                if service:
                    self._service_errors.append(error)
                raise

        task = asyncio.create_task(invoke(), name=name)
        self._tasks.add(task)

        def completed(done: asyncio.Task[T]) -> None:
            self._tasks.discard(done)
            if not done.cancelled() and (error := done.exception()) is not None:
                logger.error("operation %s failed", name, exc_info=error)

        task.add_done_callback(completed)
        return task

    async def run(self, operation: Callable[[], Awaitable[T]], *, name: str) -> T:
        return await asyncio.shield(self.start(operation, name=name))

    async def run_blocking(self, operation: Callable[[], T], *, name: str) -> T:
        # Continuations of admitted work must finish after admission closes.
        if self._closed:
            raise ServiceStopping("application resources are closed")
        future = asyncio.get_running_loop().run_in_executor(
            None, contextvars.copy_context().run, operation)
        self._threads[future] = name

        def completed(done: asyncio.Future[T]) -> None:
            self._threads.pop(done, None)
            if not done.cancelled() and (error := done.exception()) is not None:
                logger.error("blocking operation %s failed", name, exc_info=error)

        future.add_done_callback(completed)
        return await finish_on_cancel(future)

    def stop_admission(self) -> None:
        self._accepting = False

    def assert_drained(self) -> None:
        if self._pending():
            raise RuntimeError("application operations are active")
        if self._shutdown_task is not None and self._shutdown_task.done():
            self._shutdown_task.result()
        if self._service_errors:
            raise BaseExceptionGroup("application service failed", self._service_errors)

    def close(self) -> None:
        """Seal resource access, only after a successful drain (or before first use)."""
        self.stop_admission()
        self.assert_drained()
        self._closed = True

    def _pending(self) -> set[asyncio.Future]:
        return {work for work in (*self._tasks, *self._threads) if not work.done()}

    async def _wait(self, timeout: float) -> bool:
        deadline = asyncio.get_running_loop().time() + max(0, timeout)
        while pending := self._pending():
            remaining = max(0, deadline - asyncio.get_running_loop().time())
            _, unfinished = await asyncio.wait(pending, timeout=remaining)
            if unfinished:
                return False
        return True

    async def _drain(self, grace_timeout: float, cancel_timeout: float) -> None:
        if not await self._wait(grace_timeout):
            for task in tuple(self._tasks):
                if not task.done():
                    task.cancel()
            if not await self._wait(cancel_timeout):
                names = sorted({task.get_name() for task in self._tasks if not task.done()}
                               | {name for work, name in self._threads.items() if not work.done()})
                raise ShutdownTimeout(f"operations did not stop before shutdown deadline: {', '.join(names)}")
        self.close()

    async def shutdown(self, *, grace_timeout: float = GRACE_TIMEOUT,
                       cancel_timeout: float = CANCEL_TIMEOUT) -> None:
        self.stop_admission()
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._drain(grace_timeout, cancel_timeout), name="application-shutdown")

            def completed(done: asyncio.Task[None]) -> None:
                if not done.cancelled() and (error := done.exception()) is not None:
                    logger.error("application shutdown failed; resources remain open", exc_info=error)
            self._shutdown_task.add_done_callback(completed)
        await asyncio.shield(self._shutdown_task)
