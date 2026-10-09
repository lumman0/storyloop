"""Copied into a clean directory by test_platform_wheel; no test-suite imports."""
import asyncio
from importlib import metadata, util
import json
from pathlib import Path

assert util.find_spec("story_harness") is None
assert "story-harness" not in {item.metadata["Name"] for item in metadata.distributions()}
import storyloop_platform
from storyloop_platform.cli import portal_api
from storyloop_platform.adapters.runtime_config import HarnessConfig
from storyloop_platform.portal.http_api import create_app
from storyloop_platform.portal.service import PlayerPortal
from storyloop_harness.testing import OfflineModel
from fastapi.testclient import TestClient

root = Path.cwd()
for retired in ("react_play", "live_play", "campaign_play", "demo_check", "interaction_demo"):
    assert util.find_spec("storyloop_platform.cli." + retired) is None
assert "storyloop-harness<0.3,>=0.2" in metadata.requires("storyloop-platform")
assert HarnessConfig.load(Path(storyloop_platform.__file__).parent / "defaults/online.json").profile == "online"
config = Path(storyloop_platform.__file__).parent / "defaults/local.json"
settings = json.loads(config.read_text(encoding="utf-8"))
settings["billing"]["models"]["offline"] = {
    "input_rmb_per_million": "1", "output_rmb_per_million": "1", "multiplier": "1"}
(root / "local.json").write_text(json.dumps(settings), encoding="utf-8")
(root / "catalog.json").write_text(json.dumps({"games": [
    {"id": "offline", "title": "Offline", "mode": "freeform", "package": "scenario"}
]}), encoding="utf-8")
HarnessConfig.create_model = lambda *args, **kwargs: OfflineModel()
portal = PlayerPortal(root / "catalog.json", root / "local.json", str(root / "world.sqlite3"),
                      prologue_generator=lambda *_: "A quiet opening.")
try:
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        token = portal.register("reader", "password-123")["token"]
        game = asyncio.run(portal.create_save(token, "offline"))["game_id"]
        before = portal.store.load(game).version
        result = client.post(f"/v1/saves/{game}/turns",
                             headers={"Authorization": f"Bearer {token}"},
                             json={"text": "Hello", "request_id": "wheel-turn"})
        assert result.status_code == 200, result.text
        assert result.json()["body"].strip()
        assert portal.store.load(game).version > before
        assert portal.store.event_exists(game, "portal-wheel-turn:input")
finally:
    portal.close()
print("offline player turn passed")
