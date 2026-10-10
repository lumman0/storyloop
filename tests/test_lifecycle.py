"""Application ownership follows actual tasks and executor invocations."""

import asyncio
import threading

import pytest


def supervisor():
    from storyloop_platform.lifecycle import OperationSupervisor
    return OperationSupervisor()


def test_rejected_factory_is_never_called_and_cancelled_waiter_keeps_work_owned():
    async def run():
        from storyloop_platform.lifecycle import ServiceStopping
        operations = supervisor()
        entered, release = asyncio.Event(), asyncio.Event()
        async def work():
            entered.set()
            await release.wait()
            return 42
        waiter = asyncio.create_task(operations.run(work, name="model"))
        await entered.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(RuntimeError, match="active"):
            operations.assert_drained()
        operations.stop_admission()
        with pytest.raises(ServiceStopping):
            operations.start(lambda: pytest.fail("factory called"), name="late")
        release.set()
        await operations.shutdown()
        operations.assert_drained()
    asyncio.run(run())


def test_real_thread_survives_repeated_cancellation_and_shutdown_deadline(caplog):
    async def run():
        from storyloop_platform.lifecycle import ShutdownTimeout
        operations = supervisor()
        entered, release = threading.Event(), threading.Event()
        def work():
            entered.set()
            assert release.wait(5)
            raise ValueError("late thread failure")
        task = operations.start(lambda: operations.run_blocking(work, name="provider"), name="memory")
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(ShutdownTimeout):
                await operations.shutdown(grace_timeout=0, cancel_timeout=0.01)
            assert not task.done()
            with pytest.raises(RuntimeError, match="active"):
                operations.assert_drained()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        with pytest.raises(ShutdownTimeout):
            await operations.shutdown(grace_timeout=10)
        assert "late thread failure" in caplog.text
    asyncio.run(run())


def test_cancelled_shutdown_waiter_does_not_abort_shared_drain():
    async def run():
        operations = supervisor()
        release = asyncio.Event()
        task = operations.start(release.wait, name="model")
        first = asyncio.create_task(operations.shutdown())
        await asyncio.sleep(0)
        assert not operations.accepting
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(operations.shutdown(grace_timeout=0))
        await asyncio.sleep(0)
        assert not second.done() and not task.cancelled()
        release.set()
        await second
    asyncio.run(run())


def test_service_failure_is_logged_and_shutdown_reports_it(caplog):
    async def run():
        operations = supervisor()
        async def failed():
            raise ValueError("worker broke")
        task = operations.start(failed, name="worker", service=True)
        with pytest.raises(ValueError):
            await task
        with pytest.raises(ExceptionGroup, match="service"):
            await operations.shutdown()
        assert "worker broke" in caplog.text
    asyncio.run(run())


def test_shutdown_cannot_overtake_service_failure_callback():
    async def run():
        operations = supervisor()
        async def failed():
            raise ValueError("immediate worker failure")
        operations.start(failed, name="worker", service=True)
        # Drain may run after the worker finishes but before its done callback.
        with pytest.raises(ExceptionGroup, match="service"):
            await operations.shutdown()
    asyncio.run(run())
