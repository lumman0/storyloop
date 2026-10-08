"""A failed settlement must not lose the completed turn's original metering."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from story_harness.core.billing import record_model_usage
from story_harness.core.contracts import WorldEvent
from story_harness.portal.service import PlayerPortal
from story_harness.runtime.player_input import submit_player_input
from test_turn_failure_contract import portal, ROOT


def completed_session(portal):
    class Session:
        calls = 0

        async def run_turn(self, game_id, text, turn_id, progress=None):
            self.calls += 1
            record_model_usage("qwen3.8-flash", "npc_selection", SimpleNamespace(
                input_tokens=1000, output_tokens=500,
                metadata={"prompt_tokens_details": {"cached_tokens": 200}},
            ))
            snapshot = submit_player_input(portal.store, game_id, f"{turn_id}:input", text)
            return SimpleNamespace(narration="原始完成正文", segments=(), snapshot=snapshot)

        async def run_ready_work(self, game_id):
            pass

    session = Session()
    portal._react = lambda *args, **kwargs: session
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
    version = portal.store.load(game_id).version
    assert session.calls == 1
    db_path = portal.db_path
    portal.close()
    reopened = PlayerPortal(ROOT / "config/games.example.json", ROOT / "config/local.json", db_path)
    try:
        def no_models(*args, **kwargs):
            raise AssertionError("settlement recovery must not call a story model")

        reopened._react = no_models
        reopened.billing.policy = replace(reopened.billing.policy, pricing_version="new-price",
                                           points_per_rmb=999)
        result = asyncio.run(reopened.turn(token, game_id, "你好", "recover"))
        assert result["body"] == "原始完成正文"
        assert result["billing"]["input_tokens"] == 1000
        assert result["billing"]["output_tokens"] == 500
        assert result["billing"]["charged_points"] == "0.101"
        assert reopened.store.load(game_id).version == version
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
    before = portal.store.load(game_id)
    portal.store.commit(game_id, before.version, WorldEvent(
        f"portal-legacy:{kind}", "recovered_operation", "player", None, before.tick, (),
        {"text": "你好", "request_text": "你好"}), (), ())
    billing = portal.billing
    if not billing_enabled:
        portal.billing = None
    with pytest.raises(ValueError, match="恢复|recover"):
        asyncio.run(portal.turn(token, game_id, "你好", "legacy"))
    player_id = portal.accounts.resolve_token(token)
    assert all(item["kind"] != "turn" for item in billing.ledger(player_id))


def test_failed_snapshot_write_requires_recovery_without_free_rebilling(portal, monkeypatch):
    token = portal.register("reader", "password-123")["token"]
    game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    session = completed_session(portal)
    monkeypatch.setattr(portal.turn_settlements, "prepare", fail_settlement)
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
    portal.billing = None
    result = asyncio.run(portal.turn(token, game_id, "你好", "prepared"))
    assert result["billing"]["input_tokens"] == 1000
    assert result["billing"]["charged_points"] == "0.101"
    assert session.calls == 1


def test_platform_always_assembles_single_call_session(portal):
    from story_harness.runtime.single_call import SingleCallGameSession
    from story_harness.world.scenario import ScenarioPackage

    package = ScenarioPackage.load(ROOT / "examples/freeform")
    package.seed_game(portal.store, "assembly")
    item = SimpleNamespace(package_path=str(ROOT / "examples/freeform"), turns_per_story_tick=1)
    # An old in-memory configuration cannot select new beta execution.
    portal.config = replace(portal.config, runtime=replace(portal.config.runtime,
                                                          turn_engine="multi_agent_beta"))
    assert isinstance(portal._react(item, package, "assembly"), SingleCallGameSession)


def test_platform_recovers_legacy_npc_reply_once(portal, monkeypatch):
    from story_harness.agents.npc_agent import NpcAgentPool
    from story_harness.core.contracts import PendingWork
    from story_harness.runtime.single_call import SingleCallGameSession
    from story_harness.world.scenario import ScenarioPackage

    package = ScenarioPackage.load(ROOT / "examples/freeform")
    package.seed_game(portal.store, "legacy-work")
    before = portal.store.load("legacy-work")
    event = WorldEvent("legacy-input", "player_spoke", "player", None, before.tick, (),
                       {"text": "hello"})
    work = PendingWork("legacy-reply", "npc_reply", before.tick, 10, event.event_id,
                       {"actor_id": "dockhand", "player_message": "hello"})
    portal.store.commit("legacy-work", before.version, event, (), (work,))
    calls = []
    confirmations = []

    async def prepare_response(self, game_id, actor_id, role_card, player_message, **kwargs):
        calls.append((game_id, actor_id, player_message, kwargs["current_input_event_id"]))
        return SimpleNamespace(speech="The old reply survives.",
                               confirm=lambda: confirmations.append(work.work_id),
                               abort=lambda: None)

    monkeypatch.setattr(NpcAgentPool, "prepare_response", prepare_response)
    item = SimpleNamespace(package_path=str(ROOT / "examples/freeform"), turns_per_story_tick=1)
    session = portal._react(item, package, "legacy-work")
    assert isinstance(session, SingleCallGameSession)
    asyncio.run(session.run_ready_work("legacy-work"))
    asyncio.run(session.run_ready_work("legacy-work"))
    assert calls == [("legacy-work", "dockhand", "hello", "legacy-input")]
    assert confirmations == ["legacy-reply"]
    assert all(item.kind != "npc_reply" for item in portal.store.pending_work("legacy-work"))
    assert portal.store.event_exists("legacy-work", "legacy-reply:spoken")
    assert any("The old reply survives." in item.content
               for item in portal.store.observations_for("legacy-work", "player"))
