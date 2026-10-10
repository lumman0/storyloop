"""Reviewer gameplay borrows execution while excluding billing and player profiles."""

import asyncio

import pytest

from test_scenario_lifecycle_concurrency import archive
from test_turn_failure_contract import portal


def test_review_preview_is_permission_checked_unbilled_profile_free_and_limited(portal, monkeypatch):
    author = portal.register("preview-author", "password-123")
    reviewer = portal.register("preview-admin", "password-123")
    portal.access.bootstrap_admin("preview-admin")
    draft = portal.upload_scenario(author["token"], "Preview", "", archive())
    submission = portal.submit_scenario(author["token"], draft["id"])
    with pytest.raises(PermissionError):
        asyncio.run(portal.create_review_preview(author["token"], submission["submission_id"]))
    before = portal.wallet(reviewer["token"])
    preview = asyncio.run(portal.create_review_preview(reviewer["token"], submission["submission_id"]))
    game_id = preview["game_id"]

    async def no_preferences(*args):
        raise AssertionError("review preview cannot read player preferences")
    def forbidden(*args):
        raise AssertionError("review preview cannot queue profiles or require credit")
    monkeypatch.setattr(portal.memory_service, "preferences_for", no_preferences)
    monkeypatch.setattr(portal.memory_service, "queue_input", forbidden)
    monkeypatch.setattr(portal.billing, "require_credit", forbidden)
    async def run():
        for index in range(12):
            response = await portal.turn(reviewer["token"], game_id, "Hello", f"preview-{index}")
            assert "billing" not in response
        assert await portal.turn(reviewer["token"], game_id, "Hello", "preview-0") == portal.history(reviewer["token"], game_id)["turns"][0]["response"]
        with pytest.raises(ValueError, match="12-turn limit"):
            await portal.turn(reviewer["token"], game_id, "Hello", "preview-12")
    asyncio.run(run())
    assert portal.wallet(reviewer["token"]) == before
    assert portal.moderation.preview_turn_count(game_id) == 12
    assert portal.turns.settlements.get(game_id, "preview-0", "Hello") is None
