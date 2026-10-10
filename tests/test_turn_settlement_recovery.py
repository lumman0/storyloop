"""A failed settlement must not lose the completed turn's original metering."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from storyloop_platform.portal.billing import record_model_usage
from storyloop_harness.advanced import WorldEvent
from storyloop_platform.config import load_settings
from storyloop_platform.bootstrap import build_portal
from runtime_fakes import OfflineExecutor, offline_runtime_builder, turn_outcome
from storyloop_harness import ScenarioPackage
from committed_input import commit_player_input
from test_turn_failure_contract import portal, ROOT


def completed_session(portal):
    class Session(OfflineExecutor):
        calls = 0

        def proposed_options(self, *args):
            return ()

        async def run_turn(self, turn, *, progress=None, max_tick=None):
            game_id, text, turn_id = turn.game_id, turn.player_text, turn.turn_id
            self.calls += 1
            record_model_usage("qwen3.8-flash", "followup_actions", SimpleNamespace(
                input_tokens=1000, output_tokens=500,
                metadata={"prompt_tokens_details": {"cached_tokens": 200}},
            ))
            snapshot = commit_player_input(portal.gameplay.store, game_id, f"{turn_id}:input", text)
            return turn_outcome(snapshot, "原始完成正文")

    item = next(iter(portal.gameplay.game_access.catalog.list_games()))
    session = Session(portal.gameplay.store, ScenarioPackage.load(item.package_path))
    portal.gameplay.factory.executor_builder = lambda *args, **kwargs: session
    return session


def fail_settlement(*args, **kwargs):
    raise RuntimeError("settlement connection unavailable")


def test_settlement_recovers_after_restart_without_models_or_repricing(portal, monkeypatch):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    session = completed_session(portal)
    monkeypatch.setattr(portal.billing, "settle_turn", fail_settlement)
    with pytest.raises(RuntimeError, match="settlement connection"):
        asyncio.run(portal.turn(token, game_id, "你好", "recover"))
    version = portal.gameplay.store.load(game_id).version
    assert session.calls == 1
    db_path = portal.db_path
    portal.close()
    def no_models(*args, **kwargs):
        raise AssertionError("settlement recovery must not call a story model")
    reopened = build_portal(ROOT / "examples/catalog.json", load_settings(ROOT / "config/local.json"), db_path,
                            runtime_factory_builder=offline_runtime_builder(executor_builder=no_models))
    try:
        reopened.billing.policy = replace(reopened.billing.policy, pricing_version="new-price",
                                           points_per_rmb=999)
        result = asyncio.run(reopened.turn(token, game_id, "你好", "recover"))
        assert result["body"] == "原始完成正文"
        assert result["billing"]["input_tokens"] == 1000
        assert result["billing"]["output_tokens"] == 500
        assert result["billing"]["charged_points"] == "0.101"
        assert reopened.gameplay.store.load(game_id).version == version
        assert asyncio.run(reopened.turn(token, game_id, "你好", "recover")) == result
        assert len([item for item in reopened.credit_ledger(token) if item["kind"] == "turn"]) == 1
        with pytest.raises(ValueError, match="different input"):
            asyncio.run(reopened.turn(token, game_id, "different", "recover"))
    finally:
        reopened.close()


@pytest.mark.parametrize("kind", ["input", "query", "action", "continue", "choice", "advance", "completed"])
@pytest.mark.parametrize("billing_enabled", [True, False])
def test_legacy_world_commit_without_usage_is_not_silently_billed_as_zero(portal, kind, billing_enabled):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    completed_session(portal)
    before = portal.gameplay.store.load(game_id)
    portal.gameplay.store.commit(game_id, before.version, WorldEvent(
        f"portal-legacy:{kind}", "recovered_operation", "player", None, before.tick, (),
        {"text": "你好", "request_text": "你好"}), (), ())
    billing = portal.billing
    if not billing_enabled:
        portal.turns.billing = None
    with pytest.raises(ValueError, match="恢复|recover"):
        asyncio.run(portal.turn(token, game_id, "你好", "legacy"))
    player_id = portal.accounts.resolve_token(token)
    assert all(item["kind"] != "turn" for item in billing.ledger(player_id))


def test_failed_snapshot_write_requires_recovery_without_free_rebilling(portal, monkeypatch):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    session = completed_session(portal)
    monkeypatch.setattr(portal.turns.settlements, "prepare", fail_settlement)
    with pytest.raises(RuntimeError, match="settlement connection"):
        asyncio.run(portal.turn(token, game_id, "你好", "snapshot-failure"))
    with pytest.raises(ValueError, match="恢复"):
        asyncio.run(portal.turn(token, game_id, "你好", "snapshot-failure"))
    assert session.calls == 1
    assert all(item["kind"] != "turn" for item in portal.credit_ledger(token))


def test_lost_response_after_settlement_does_not_charge_again(portal, monkeypatch):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    session = completed_session(portal)
    settle = portal.billing.settle_turn

    def commit_then_disconnect(*args, **kwargs):
        settle(*args, **kwargs)
        raise RuntimeError("response disconnected")

    monkeypatch.setattr(portal.billing, "settle_turn", commit_then_disconnect)
    with pytest.raises(RuntimeError, match="response disconnected"):
        asyncio.run(portal.turn(token, game_id, "你好", "lost-response"))
    result = asyncio.run(portal.turn(token, game_id, "你好", "lost-response"))
    assert result["billing"]["charged_points"] == "0.101"
    assert session.calls == 1
    assert len([item for item in portal.credit_ledger(token) if item["kind"] == "turn"]) == 1


def test_prepared_turn_cannot_change_input_and_can_settle_after_billing_disabled(portal, monkeypatch):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    session = completed_session(portal)
    monkeypatch.setattr(portal.billing, "settle_turn", fail_settlement)
    with pytest.raises(RuntimeError, match="settlement connection"):
        asyncio.run(portal.turn(token, game_id, "你好", "prepared"))
    with pytest.raises(ValueError, match="different input"):
        asyncio.run(portal.turn(token, game_id, "different", "prepared"))
    db_path = portal.db_path
    portal.close()
    def forbidden(*args, **kwargs):
        raise AssertionError("prepared replay must precede model and credit work")
    reopened = build_portal(ROOT / "examples/catalog.json",
                            portal.settings.model_copy(update={"credits": None}), db_path,
                            runtime_factory_builder=offline_runtime_builder(executor_builder=forbidden))
    try:
        assert reopened.billing is None and reopened.turns.billing is None
        result = asyncio.run(reopened.turn(token, game_id, "你好", "prepared"))
        assert result["billing"]["input_tokens"] == 1000
        assert result["billing"]["charged_points"] == "0.101"
        assert session.calls == 1
        assert asyncio.run(reopened.turn(token, game_id, "你好", "prepared")) == result
        player_id = reopened.accounts.resolve_token(token)
        billing = reopened.turns.billing_for_policy(portal.billing.policy)
        assert billing.engine is reopened.accounts.engine
        assert len([entry for entry in billing.ledger(player_id) if entry["kind"] == "turn"]) == 1
    finally:
        reopened.close()


def test_platform_always_assembles_single_call_session(portal):
    from storyloop_harness import TurnEngine
    from storyloop_harness import ScenarioPackage

    package = ScenarioPackage.load(ROOT / "examples/freeform")
    package.seed_game(portal.gameplay.store, "assembly")
    item = SimpleNamespace(package_path=str(ROOT / "examples/freeform"), turns_per_story_tick=1)
    assert isinstance(portal.gameplay.factory.engine(item, package, "assembly"), TurnEngine)
