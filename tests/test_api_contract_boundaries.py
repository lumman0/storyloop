"""Malformed output gives no permission to discard or resubmit a pending action."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app
from test_turn_failure_contract import portal


@pytest.mark.parametrize("stream", [False, True])
def test_invalid_final_view_is_unknown_even_after_a_real_committed_turn(portal, stream):
    from test_platform_harness_integration import PricedOfflineModel
    portal.gameplay.factory.offline_models.model = PricedOfflineModel()
    token = portal.register("reader", "password-123")["token"]
    game = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
    original = portal.turn

    async def invalid(*args, **kwargs):
        view = await original(*args, **kwargs)
        del view["state_version"]
        return view

    portal.turn = invalid
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        response = client.post(f"/v1/saves/{game}/turns" + ("/stream" if stream else ""),
                               headers={"Authorization": f"Bearer {token}"},
                               json={"text": "Hello", "request_id": "contract-turn"})
        payload = ([json.loads(line[6:]) for line in response.text.splitlines()
                    if line.startswith("data: ")][-1] if stream else response.json())
        assert response.status_code == (200 if stream else 500)
        assert payload["commit_state"] == "unknown"
        assert payload["request_id"] == "contract-turn"
        assert "state_version" not in payload["message"]
        assert portal.gameplay.store.event_exists(game, "portal-contract-turn:input")
        assert len([row for row in portal.credit_ledger(token) if row["kind"] == "turn"]) == 1
        portal.turn = original
        replay = client.post(f"/v1/saves/{game}/turns", headers={"Authorization": f"Bearer {token}"},
                             json={"text": "Hello", "request_id": "contract-turn"})
        assert replay.status_code == 200
        assert "state_version" in replay.json()
        assert len([row for row in portal.credit_ledger(token) if row["kind"] == "turn"]) == 1


@pytest.mark.parametrize("event", [dict(type="future", stage="thinking"), dict(type="preview", segments=[])])
def test_invalid_progress_emits_valid_unknown_terminal_error(portal, event):
    token = portal.register("reader", "password-123")["token"]
    view = asyncio.run(portal.create_save(token, "npc-chat"))

    async def progress_turn(*args, progress=None):
        await progress(event)
        return view

    portal.turn = progress_turn
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        response = client.post(f"/v1/saves/{view['game_id']}/turns/stream",
                               headers={"Authorization": f"Bearer {token}"},
                               json={"text": "Hello", "request_id": "bad-progress"})
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert [item["type"] for item in events] == ["stage", "error"]
    assert events[-1]["commit_state"] == "unknown"
    assert events[-1]["request_id"] == "bad-progress"
