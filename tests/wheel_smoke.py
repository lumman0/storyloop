"""Copied into a clean directory by test_platform_wheel; no test-suite imports."""
import asyncio
import json
from importlib import metadata, util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

assert util.find_spec("story_harness") is None
assert "story-harness" not in {item.metadata["Name"] for item in metadata.distributions()}
from fastapi.testclient import TestClient
from storyloop_harness.testing import OfflineModel

from storyloop_platform.config import ModelFactory, default_settings, load_settings
from storyloop_platform.portal.billing import record_model_usage
from storyloop_platform.portal.http_api import create_app
from storyloop_platform.bootstrap import build_portal
from storyloop_platform.gameplay.factory import RuntimeFactory

root = Path.cwd().resolve()
for retired in ("react_play", "live_play", "campaign_play", "demo_check", "interaction_demo", "bailian_smoke"):
    assert util.find_spec("storyloop_platform.cli." + retired) is None
assert "storyloop-harness<0.3,>=0.2" in metadata.requires("storyloop-platform")
local = default_settings()
online = default_settings("online")
assert local.environment == "local" and local.storage.driver == "sqlite"
assert local.storage.path == str(root / "story-game.sqlite3")
assert local.player_memory.driver == "none"
assert online.environment == "online" and online.storage.url_env == "DATABASE_URL"
assert online.player_memory.driver == "mem0"
assert online.model_for("single_turn").model == local.model_for("single_turn").model
(root / "local.json").write_text(json.dumps({
    "providers": {"offline": {"base_url": "https://offline.invalid/v1",
                              "api_key_env": "STORY_MODEL_API_KEY"}},
    "models": {"offline": {"kind": "chat", "provider": "offline", "model": "offline",
        "rate": {"pricing_version": "wheel-offline-1", "input_rmb_per_million": "0.8",
                 "output_rmb_per_million": "2.7", "cached_input_rmb_per_million": "0.1",
                 "multiplier": "1"}}},
    "routes": {task: "offline" for task in local.routes},
    "storage": {"path": "world.sqlite3"},
}), encoding="utf-8")
settings = load_settings(root / "local.json")
assert set(settings.providers) == set(settings.models) == {"offline"}
assert set(settings.routes.values()) == {"offline"}
assert settings.storage.path == str(root / "world.sqlite3")
(root / "catalog.json").write_text(json.dumps({"games": [
    {"id": "offline", "title": "Offline", "mode": "freeform", "package": "scenario"}
]}), encoding="utf-8")
class PricedOfflineModel(OfflineModel):
    async def __call__(self, *args, **kwargs):
        result = await super().__call__(*args, **kwargs)
        record_model_usage("offline", "single_turn", SimpleNamespace(
            input_tokens=1000, output_tokens=500,
            metadata=SimpleNamespace(prompt_tokens_details={"cached_tokens": 200}),
        ))
        return result


class OfflineModels:
    def require_credentials(self):
        pass
    def create_model(self, task, *, temperature=None):
        assert settings.model_for(task).model == "offline"
        return PricedOfflineModel()


def offline_runtime(**dependencies):
    dependencies["models"] = OfflineModels()
    return RuntimeFactory(**dependencies)


portal = build_portal(root / "catalog.json", settings,
                      prologue_generator=AsyncMock(return_value='A quiet opening.'),
                      runtime_factory_builder=offline_runtime)
try:
    with TestClient(
        create_app(portal), base_url="http://127.0.0.1"
    ) as client:
        token = portal.register("reader", "password-123")["token"]
        game = asyncio.run(portal.create_save(token, "offline"))["game_id"]
        before = portal.gameplay.store.load(game).version
        result = client.post(f"/v1/saves/{game}/turns",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"text": "Hello", "request_id": "wheel-turn"})
        assert result.status_code == 200, result.text
        assert result.json()["body"].strip()
        assert portal.gameplay.store.load(game).version > before
        assert portal.gameplay.store.event_exists(game, "portal-wheel-turn:input")
        assert result.json()["billing"]["charged_points"] == "0.101"
        assert portal.wallet(token)["balance_points"] == "499.899"
        ledger = portal.credit_ledger(token)
        assert len(ledger) == 2 and ledger[0]["pricing_version"] == "wheel-offline-1"
        assert all(item["model"] == "offline" for item in ledger[0]["usage"])
        replay = client.post(f"/v1/saves/{game}/turns",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"text": "Hello", "request_id": "wheel-turn"})
        assert replay.status_code == 200 and replay.json() == result.json()
        assert len(portal.credit_ledger(token)) == 2
finally:
    portal.close()
print("offline player turn passed")
