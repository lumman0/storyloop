"""Real bootstrap ownership across HTTP, uploads, memory, and resource disposal."""

import asyncio
import inspect
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import event, text

from storyloop_platform.bootstrap import build_portal
from storyloop_platform.config import load_settings
from storyloop_platform.lifecycle import ServiceStopping, ShutdownTimeout
from storyloop_platform.portal.http_api import create_app
from test_scenario_lifecycle_concurrency import archive
from runtime_fakes import OfflineRuntimeFactory

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_portal(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("STORY_MODEL_API_KEY", "offline-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    async def generate(*args):
        return "A quiet opening."
    portal = build_portal(ROOT / "examples/catalog.json", load_settings(ROOT / "config/local.json"),
                          str(tmp_path / "portal.sqlite3"), prologue_generator=generate,
                          runtime_factory_builder=OfflineRuntimeFactory)
    yield portal
    try:
        portal.close()
    except (ShutdownTimeout, ExceptionGroup):
        # Test explicitly releases surviving work before teardown. A terminal failed
        # application shutdown never automatically disposes these resources.
        portal.accounts.engine.dispose()


def test_async_commands_and_bootstrap_own_same_supervisor(app_portal):
    assert inspect.iscoroutinefunction(app_portal.upload_scenario)
    assert inspect.iscoroutinefunction(app_portal.upload_scenario_version)
    assert app_portal.memory_service.operations is app_portal.operations
    assert app_portal.user_scenarios.operations is app_portal.operations


@pytest.mark.parametrize("method,http_method,path,body", [
    ("create_save", "POST", "/v1/saves", {"catalog_id": "npc-chat"}),
    ("resume_save", "POST", "/v1/saves/game/resume", None),
    ("create_review_preview", "POST", "/v1/manage/submissions/submission/preview", None),
    ("turn", "POST", "/v1/saves/game/turns", {"text": "hello", "request_id": "new"}),
    ("turn", "POST", "/v1/saves/game/turns/stream", {"text": "hello", "request_id": "new"}),
    ("memory_status", "GET", "/v1/me/memory", None),
    ("set_memory_enabled", "POST", "/v1/me/memory/settings", {"enabled": True}),
    ("clear_memory", "DELETE", "/v1/me/memory", None),
    ("set_save_settings", "PUT", "/v1/saves/game/settings", {"temperature": 0.8, "context_window_tokens": 8192}),
])
def test_http_admits_owned_operation_and_shutdown_rejects_late_work(app_portal, method, http_method, path, body):
    async def run():
        token = app_portal.register("reader", "password-123")["token"]
        entered, release = asyncio.Event(), asyncio.Event()
        async def work(*args, **kwargs):
            entered.set()
            await release.wait()
            return {"ok": True}
        setattr(app_portal, method, work)
        app = create_app(app_portal)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            request = asyncio.create_task(client.request(http_method, path, json=body, headers={"Authorization": f"Bearer {token}"}))
            try:
                await asyncio.wait_for(entered.wait(), 1)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
                with pytest.raises(RuntimeError, match="active"):
                    app_portal.close()
                shutdown = asyncio.create_task(app_portal.shutdown())
                await asyncio.sleep(0)
                response = await client.request(http_method, path, json=body, headers={"Authorization": f"Bearer {token}"})
                assert response.status_code == 503
                assert response.json()["code"] == "SERVICE_STOPPING"
                if method == "turn":
                    assert response.json()["commit_state"] == "not_started"
                    assert response.json()["request_id"] == "new"
            finally:
                release.set()
                await asyncio.gather(request, return_exceptions=True)
                await app_portal.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize("stream", [False, True])
def test_disconnected_http_model_completes_with_one_receipt_and_charge(app_portal, stream):
    from storyloop_harness.testing import OfflineModel
    from storyloop_harness.usage import record_model_usage

    async def run():
        portal = app_portal
        token = portal.register("reader", "password-123")["token"]
        game_id = (await portal.create_save(token, "npc-chat"))["game_id"]
        entered, release = asyncio.Event(), asyncio.Event()
        class Model(OfflineModel):
            calls = 0
            async def __call__(self, *args, **kwargs):
                self.calls += 1
                entered.set()
                await release.wait()
                record_model_usage("qwen3.8-flash", "single_turn", SimpleNamespace(
                    input_tokens=1000, output_tokens=500))
                return await super().__call__(*args, **kwargs)
        portal.billing.policy = replace(portal.billing.policy, rates={
            **portal.billing.policy.rates, "offline": portal.billing.policy.rates["qwen3.8-flash"]})
        model = Model()
        portal.gameplay.factory.offline_models.model = model
        portal.gameplay.factory.invalidate(game_id)
        app = create_app(portal)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1") as client:
            path = f"/v1/saves/{game_id}/turns"
            kwargs = {"json": {"text": "Hello", "request_id": "disconnect"},
                      "headers": {"Authorization": f"Bearer {token}"}}
            request = asyncio.create_task(client.post(path + ("/stream" if stream else ""), **kwargs))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
                with pytest.raises(RuntimeError, match="active"):
                    portal.operations.assert_drained()
            finally:
                release.set()
            # Retrying while the original completes waits on the same player lock.
            first = await client.post(path, **kwargs)
            assert first.status_code == 200, first.text
            calls = model.calls
            second = await client.post(path, **kwargs)
            assert second.json() == first.json()
            assert model.calls == calls
            assert float(first.json()["billing"]["charged_points"]) > 0
            assert len([row for row in portal.credit_ledger(token) if row["kind"] == "turn"]) == 1
            with portal.accounts.engine.connect() as db:
                assert db.execute(text("SELECT COUNT(*) FROM portal_turns WHERE game_id=:game"),
                                  {"game": game_id}).scalar_one() == 1
        await portal.shutdown()
    asyncio.run(run())


def test_blocked_upload_thread_times_out_without_disposal_then_cleans_stage(app_portal, monkeypatch):
    from storyloop_platform.portal import user_scenarios

    async def run():
        portal = app_portal
        token = portal.register("author", "password-123")["token"]
        entered, release = threading.Event(), threading.Event()
        disposed = Mock()
        event.listen(portal.accounts.engine, "engine_disposed", disposed)
        extract = user_scenarios._extract_package
        def blocked(*args):
            entered.set()
            assert release.wait(5)
            assert not disposed.called
            extract(*args)
        monkeypatch.setattr(user_scenarios, "_extract_package", blocked)
        task = portal.operations.start(lambda: portal.upload_scenario(token, "Story", "", archive()), name="upload")
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            start = asyncio.get_running_loop().time()
            with pytest.raises(ShutdownTimeout, match="upload"):
                await portal.shutdown(grace_timeout=0.01, cancel_timeout=0.01)
            assert asyncio.get_running_loop().time() - start < 0.5
            assert not disposed.called and not task.done()
            with pytest.raises(RuntimeError, match="active"):
                portal.close()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
        assert list((portal.user_scenarios.directory / ".staging").iterdir()) == []
        assert portal.my_scenarios(token) == []
        with pytest.raises(ShutdownTimeout):
            await portal.shutdown()
        assert not disposed.called
    asyncio.run(run())


@pytest.mark.parametrize("busy,expires", [(False, False), (True, False), (True, True)])
def test_lifespan_stops_memory_worker_and_drains_claimed_thread_before_close(app_portal, busy, expires):
    from storyloop_platform.memory.jobs import MemoryBatch
    from test_player_memory_service import FakeMemory, FakeJobs

    async def run():
        portal = app_portal
        provider, jobs = FakeMemory(), FakeJobs()
        service = portal.memory_service
        service.provider, service.jobs, service.enabled = provider, jobs, True
        entered, release = threading.Event(), threading.Event()
        def remember(*args):
            entered.set()
            assert release.wait(5)
            assert not provider.closed
        provider.remember = remember
        batch = MemoryBatch("player", (("game", "request", "preference"),))
        if busy:
            jobs.batches.append(batch)
        disposed = Mock()
        event.listen(portal.accounts.engine, "engine_disposed", disposed)
        app = create_app(portal, operation_shutdown_timeout=0.01 if expires else 1,
                         operation_cancel_timeout=0.01)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        try:
            if busy:
                assert await asyncio.to_thread(entered.wait, 2)
            shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
            await asyncio.sleep(0)
            if busy:
                assert not provider.closed and not disposed.called and not shutdown.done()
            if expires:
                with pytest.raises(ShutdownTimeout):
                    await asyncio.wait_for(shutdown, 0.5)
                assert not provider.closed and not disposed.called
        finally:
            release.set()
        if expires:
            assert await asyncio.to_thread(jobs.settled.wait, 2)
            # A failed shutdown remains failed even after the protected batch settles.
            await asyncio.sleep(0.01)
            assert not provider.closed and not disposed.called
            with pytest.raises(ShutdownTimeout):
                await portal.shutdown()
        else:
            await asyncio.wait_for(shutdown, 1)
            assert provider.closed and disposed.call_count == 1
        assert jobs.completed == ([batch] if busy else [])
    asyncio.run(run())


def test_cancelled_portal_shutdown_waiter_still_closes_once_after_work(app_portal):
    async def run():
        portal = app_portal
        release = asyncio.Event()
        portal.operations.start(release.wait, name="model")
        disposed = Mock()
        event.listen(portal.accounts.engine, "engine_disposed", disposed)
        first = asyncio.create_task(portal.shutdown())
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not disposed.called
        release.set()
        await portal.shutdown(grace_timeout=0)
        await portal.shutdown()
        portal.close()
        assert disposed.call_count == 1
        with pytest.raises(ServiceStopping):
            await portal.operations.run_blocking(lambda: pytest.fail("ran after close"), name="late")
    asyncio.run(run())


def test_lifespan_reports_unexpected_memory_worker_failure(app_portal, caplog):
    async def run():
        portal = app_portal
        entered = asyncio.Event()
        async def failed_worker():
            entered.set()
            raise RuntimeError("unexpected memory failure")
        portal.memory_service.run_worker = failed_worker
        app = create_app(portal)
        with pytest.raises(ExceptionGroup, match="service"):
            async with app.router.lifespan_context(app):
                await entered.wait()
        assert "unexpected memory failure" in caplog.text
    asyncio.run(run())


@pytest.mark.parametrize("version", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
def test_upload_prologue_shutdown_keeps_resources_open_and_cleans_stage(app_portal, monkeypatch, version, cancel):
    async def run():
        portal = app_portal
        token = portal.register("author", "password-123")["token"]
        initial = await portal.upload_scenario(token, "Story", "", archive()) if version else None
        entered, release = asyncio.Event(), asyncio.Event()
        disposed = Mock()
        event.listen(portal.accounts.engine, "engine_disposed", disposed)
        checked_out = set()
        event.listen(portal.accounts.engine, "checkout", lambda connection, record, proxy: checked_out.add(record))
        event.listen(portal.accounts.engine, "checkin", lambda connection, record: checked_out.discard(record))
        async def generate(*args):
            entered.set()
            await release.wait()
            assert not disposed.called
            return "An opening."
        portal.user_scenarios.prologue_generator = generate
        command = (lambda: portal.upload_scenario_version(token, initial["id"], "Revision", "", archive())) if version else (
            lambda: portal.upload_scenario(token, "Story", "", archive()))
        task = portal.operations.start(command, name="upload")
        await asyncio.wait_for(entered.wait(), 2)
        assert not checked_out
        stopping = asyncio.create_task(portal.shutdown(grace_timeout=0 if cancel else 1))
        await asyncio.sleep(0)
        assert not disposed.called
        with pytest.raises(ServiceStopping):
            portal.operations.start(command, name="late-upload")
        if not cancel:
            release.set()
        await stopping
        assert disposed.call_count == 1
        assert task.cancelled() if cancel else task.done()
        assert list((portal.user_scenarios.directory / ".staging").iterdir()) == []
        # Query via a fresh engine connection to count committed metadata.
        with portal.accounts.engine.connect() as db:
            count = db.execute(text("SELECT COUNT(*) FROM user_scenario_versions")).scalar_one()
        assert count == int(version) + int(not cancel)
    asyncio.run(run())
