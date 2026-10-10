"""Runtime construction remains accessible through the public factory seam."""

import pytest

from storyloop_harness import ScenarioPackage
from storyloop_harness.advanced import PendingWork
from test_turn_failure_contract import portal


def test_engine_cache_and_invalidation_are_save_scoped(portal):
    factory = portal.gameplay.factory
    item = portal.gameplay.game_access.listing_for("unused", "npc-chat")
    package = ScenarioPackage.load(item.package_path)
    for game_id in ("one", "two"):
        package.seed_game(portal.gameplay.store, game_id)
    first = factory.engine(item, package, "one")
    other = factory.engine(item, package, "two")
    assert factory.engine(item, package, "one") is first
    factory.invalidate("one")
    assert factory.engine(item, package, "one") is not first
    assert factory.engine(item, package, "two") is other
    assert factory.generation_settings("one") == factory.default_generation_settings()


def test_supported_save_guard_runs_before_engine_cache_replay(portal):
    item = portal.gameplay.game_access.listing_for("unused", "npc-chat")
    package = ScenarioPackage.load(item.package_path)
    store = portal.gameplay.store
    package.seed_game(store, "guard")
    portal.gameplay.factory.engine(item, package, "guard")
    snapshot = store.load("guard")
    store.commit("guard", snapshot.version, None, (),
                 (PendingWork("obsolete", "npc_reply", 100, 10, None, {}),))
    with pytest.raises(ValueError, match="Unsupported legacy save"):
        portal.gameplay.factory.engine(item, package, "guard")


def test_campaign_novel_presenter_reads_recent_narration_only(portal):
    item = portal.gameplay.game_access.listing_for("unused", "npc-chat")
    package = ScenarioPackage.load(item.package_path)
    for index in range(4):
        portal.accounts.store_turn_response("prose", str(index), "input", {"segments": [
            {"kind": "narration", "text": f" narration-{index}-a "},
            {"kind": "dialogue", "text": "excluded dialogue"},
            {"kind": "narration", "text": f"narration-{index}-b"},
        ]})
    presenter = portal.gameplay.factory.novel_presenter(package, "prose")
    assert presenter.recent_prose("prose") == ["narration-2-b", "narration-3-a", "narration-3-b"]
