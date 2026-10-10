"""Lifespan must finish detached turns before disposing shared resources."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import httpx
import pytest

from storyloop_platform.portal.http_api import create_app, serve


def fake_portal():
    portal = Mock()
    portal.resources = SimpleNamespace(allowed_hosts=lambda: {"127.0.0.1"})
    portal.settings = SimpleNamespace(environment="local")
    portal.memory_service = SimpleNamespace(run_worker=AsyncMock())
    return portal


def test_server_timeout_reaches_lifespan_even_when_connected_requests_do_not_finish():
    import uvicorn
    with patch("uvicorn.run") as launch:
        serve(fake_portal())
    settings = launch.call_args.kwargs
    assert settings.get("timeout_graceful_shutdown") == 30

    async def run():
        server = uvicorn.Server(uvicorn.Config(launch.call_args.args[0], timeout_graceful_shutdown=0.01))
        server.servers = []
        server.lifespan = SimpleNamespace(shutdown=AsyncMock())
        async def stuck_request():
            await asyncio.Event().wait()
        task = asyncio.create_task(stuck_request())
        server.server_state.tasks.add(task)
        server._wait_tasks_to_complete = AsyncMock(side_effect=stuck_request)
        await server.shutdown()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
        server.lifespan.shutdown.assert_awaited_once()
    asyncio.run(run())


def test_shutdown_waits_for_detached_turn_before_closing_and_rejects_new_turns():
    async def run():
        portal = fake_portal()
        app = create_app(portal)
        finish = asyncio.Event()
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        task = asyncio.create_task(finish.wait())
        app.state.active_turn_tasks.add(task)
        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await asyncio.sleep(0)
        portal.close.assert_not_called()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            for suffix in ("", "/stream"):
                response = await client.post("/v1/saves/game/turns" + suffix,
                    json={"text": "hello", "request_id": "new"}, headers={"Authorization": "Bearer token"})
                assert response.status_code == 503
                assert response.json()["commit_state"] == "not_started"
                assert response.json()["request_id"] == "new"
        portal.turn.assert_not_called()
        finish.set()
        await shutdown
        assert task.done()
        portal.close.assert_called_once()
    asyncio.run(run())


def test_shutdown_cancels_overdue_turn_before_disposing_resources():
    async def run():
        portal = fake_portal()
        app = create_app(portal, turn_shutdown_timeout=0.01)
        cancelled = asyncio.Event()
        async def turn():
            try:
                await asyncio.Event().wait()
            finally:
                portal.close.assert_not_called()
                cancelled.set()
        async with app.router.lifespan_context(app):
            task = asyncio.create_task(turn())
            app.state.active_turn_tasks.add(task)
            await asyncio.sleep(0)
        assert task.cancelled() and cancelled.is_set()
        portal.close.assert_called_once()
    asyncio.run(run())


def test_lifespan_waits_for_memory_service_worker_before_closing():
    async def run():
        portal = fake_portal()
        started, finish = asyncio.Event(), asyncio.Event()
        async def worker():
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await finish.wait()
                portal.close.assert_not_called()
                raise
        portal.memory_service = SimpleNamespace(run_worker=AsyncMock(side_effect=worker))
        app = create_app(portal)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        await started.wait()
        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        try:
            await asyncio.sleep(0)
            assert not shutdown.done()
            portal.close.assert_not_called()
        finally:
            finish.set()
            await shutdown
        portal.memory_service.run_worker.assert_awaited_once()
        portal.close.assert_called_once()
    asyncio.run(run())


def test_noncooperative_turn_prevents_unsafe_resource_close():
    async def run():
        portal = fake_portal()
        app = create_app(portal, turn_shutdown_timeout=0, turn_cancel_timeout=0.01)
        release = asyncio.Event()
        async def stubborn():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
        try:
            with pytest.raises(RuntimeError, match="turn tasks"):
                async with app.router.lifespan_context(app):
                    task = asyncio.create_task(stubborn())
                    app.state.active_turn_tasks.add(task)
                    await asyncio.sleep(0)
            portal.close.assert_not_called()
        finally:
            release.set()
            await task
    asyncio.run(run())
