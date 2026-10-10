"""Server request draining must remain bounded before application lifespan shutdown."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

from storyloop_platform.portal.http_api import serve


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
