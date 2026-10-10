from pathlib import Path

import pytest
from sqlalchemy import event

from storyloop_platform.config import load_settings


ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_shares_sql_and_gameplay_resources(tmp_path, monkeypatch):
    import storyloop_platform.bootstrap as bootstrap

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    portal = bootstrap.build_portal(ROOT / "examples/catalog.json",
                                    load_settings(ROOT / "config/local.json"),
                                    str(tmp_path / "game.sqlite3"))
    try:
        engine = portal.accounts.engine
        assert portal.gameplay.store.engine is engine
        assert portal.gameplay.generation_settings.engine is engine
        assert portal.turns.settlements.engine is engine
        assert portal.turns.billing.engine is engine
        assert portal.user_scenarios.engine is engine
        assert portal.moderation.engine is engine
        assert portal.access.engine is engine
        assert portal.invitations.engine is engine
        assert portal.memory_service.jobs.engine is engine
        assert portal.gameplay.factory is portal.turns.factory
        assert portal.gameplay.player_locks is portal.turns.player_locks
        assert portal.gameplay.game_access is portal.turns.game_access
        player = portal.register("same-engine", "password-123")
        assert portal.accounts.resolve_token(player["token"]) == player["player_id"]
        assert portal.wallet(player["token"])["balance_milli_points"] > 0
    finally:
        portal.close()


@pytest.mark.parametrize("fail_at", ["store", "runtime"])
def test_partial_construction_closes_acquired_resources(tmp_path, monkeypatch, fail_at):
    import storyloop_platform.bootstrap as bootstrap

    closed = []
    class Telemetry:
        def flush(self):
            closed.append("telemetry")
    class Provider:
        def __init__(self, *args):
            pass
        def close(self):
            closed.append("memory")

    monkeypatch.setattr(bootstrap, "configured_telemetry", Telemetry)
    monkeypatch.setattr(bootstrap, "Mem0PlayerMemory", Provider)
    create_database = bootstrap.PlatformResources.create_database
    def database(self, path):
        engine = create_database(self, path)
        event.listen(engine, "engine_disposed", lambda _: closed.append("engine"))
        return engine
    monkeypatch.setattr(bootstrap.PlatformResources, "create_database", database)
    def fail(**kwargs):
        raise RuntimeError("construction failed")
    if fail_at == "store":
        monkeypatch.setattr(bootstrap.PlatformResources, "create_store", lambda self, **kwargs: fail())
    settings = load_settings(ROOT / "config/local.json")
    settings = settings.model_copy(update={"player_memory": settings.player_memory.model_copy(update={"driver": "mem0"})})
    with pytest.raises(RuntimeError, match="construction failed"):
        bootstrap.build_portal(ROOT / "examples/catalog.json", settings,
                               str(tmp_path / "game.sqlite3"), runtime_factory_builder=fail)
    assert closed == (["telemetry", "engine"] if fail_at == "store" else
                      ["telemetry", "memory", "engine"])


def test_close_is_idempotent_and_continues_after_closer_failure(tmp_path, monkeypatch):
    import storyloop_platform.bootstrap as bootstrap

    closed = []
    class Telemetry:
        def flush(self):
            closed.append("telemetry")
            raise RuntimeError("flush failed")
    class Provider:
        def __init__(self, *args):
            pass
        def close(self):
            closed.append("memory")
            raise RuntimeError("memory close failed")
    monkeypatch.setattr(bootstrap, "configured_telemetry", Telemetry)
    monkeypatch.setattr(bootstrap, "Mem0PlayerMemory", Provider)
    settings = load_settings(ROOT / "config/local.json")
    settings = settings.model_copy(update={"player_memory": settings.player_memory.model_copy(update={"driver": "mem0"})})
    portal = bootstrap.build_portal(ROOT / "examples/catalog.json", settings,
                                    str(tmp_path / "game.sqlite3"))
    event.listen(portal.accounts.engine, "engine_disposed", lambda _: closed.append("engine"))
    with pytest.raises(ExceptionGroup) as errors:
        portal.close()
    assert [str(error) for error in errors.value.exceptions] == ["flush failed", "memory close failed"]
    portal.close()
    assert closed == ["telemetry", "memory", "engine"]


def test_runtime_injection_preserves_online_credential_preflight(tmp_path, monkeypatch):
    import storyloop_platform.bootstrap as bootstrap
    from storyloop_platform.config import default_settings

    monkeypatch.setenv("STORY_ALLOWED_HOSTS", "story.example")
    monkeypatch.setenv("STORY_MODEL_API_KEY", "")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    settings = default_settings("online")
    monkeypatch.setenv(settings.http.allowed_hosts_env, "story.example")
    reached = []
    with pytest.raises(ValueError, match="before model use"):
        bootstrap.build_portal(ROOT / "examples/catalog.json", settings,
                               runtime_factory_builder=lambda **deps: reached.append(deps))
    assert reached == []
