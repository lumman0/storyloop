"""Focused checks for optional, player-controlled memory."""

from __future__ import annotations

from pathlib import Path
from dataclasses import replace

from fastapi.testclient import TestClient

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.portal.http_api import create_app
from story_harness.portal.service import PlayerPortal
from story_harness.portal.player_memory import Mem0PlayerMemory


ROOT = Path(__file__).resolve().parents[1]


class FakePlayerMemory:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, str]]] = {}

    def list_memories(self, player_id: str) -> list[dict[str, str]]:
        return self.rows.get(player_id, [])

    def remember(self, player_id: str, inputs: tuple[str, ...]) -> None:
        self.rows[player_id] = [{"id": "m1", "text": "玩家偏好慢节奏", "created_at": ""}]

    def clear(self, player_id: str) -> None:
        self.rows.pop(player_id, None)

    def close(self) -> None:
        pass


def test_profile_is_opt_in_batched_and_scoped_to_player(tmp_path: Path) -> None:
    portal = PlayerPortal(ROOT / "config/games.example.json", ROOT / "config/local.json",
                          str(tmp_path / "game.sqlite3"))
    fake = FakePlayerMemory()
    portal.player_memory = fake
    portal.memory_feature_enabled = True
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        first = client.post("/v1/accounts", json={"username": "first-player",
                                                  "password": "password-123"}).json()
        second = client.post("/v1/accounts", json={"username": "second-player",
                                                   "password": "password-123"}).json()
        client.cookies.clear()
        auth = {"Authorization": f"Bearer {first['token']}"}
        assert client.get("/v1/me/memory", headers=auth).json()["enabled"] is False
        assert portal.memory_jobs.enqueue(first["player_id"], "g", "before", "我喜欢慢一点的故事节奏。") is False
        enabled = client.post("/v1/me/memory/settings", json={"enabled": True}, headers=auth)
        assert enabled.status_code == 200 and enabled.json()["enabled"] is True
        for index in range(6):
            assert portal.memory_jobs.enqueue(first["player_id"], "g", str(index),
                                              "我喜欢慢一点的故事节奏，先看看周围。")
        batch = portal.memory_jobs.claim()
        assert batch is not None and len(batch.items) == 6
        assert batch.player_id == first["player_id"]
        fake.remember(batch.player_id, tuple(item[2] for item in batch.items))
        portal.memory_jobs.complete(batch)
        assert client.get("/v1/me/memory", headers=auth).json()["memories"][0]["text"] == "玩家偏好慢节奏"
        other = {"Authorization": f"Bearer {second['token']}"}
        assert client.get("/v1/me/memory", headers=other).json()["memories"] == []
        portal.memory_feature_enabled = False
        disabled = client.get("/v1/me/memory", headers=auth).json()
        assert disabled["available"] is False and len(disabled["memories"]) == 1
        assert client.delete("/v1/me/memory", headers=auth).json()["memories"] == []
        assert portal.memory_jobs.pending_count(first["player_id"]) == 0


def test_server_flag_keeps_memory_off_by_default() -> None:
    config = HarnessConfig.load(ROOT / "config/online.json")
    assert config.player_memory.driver == "mem0"
    assert config.player_memory_enabled({}) is False
    assert config.player_memory_enabled({"STORY_PLAYER_MEMORY_ENABLED": "1"}) is True


def test_campaign_controls_are_not_sent_to_player_profile_memory() -> None:
    class Jobs:
        def __init__(self) -> None:
            self.inputs: list[str] = []

        def enqueue(self, _player_id: str, _game_id: str,
                    _request_id: str, player_text: str) -> bool:
            self.inputs.append(player_text)
            return False

    portal = object.__new__(PlayerPortal)
    portal.memory_feature_enabled = True
    portal.player_memory = FakePlayerMemory()
    portal.memory_jobs = Jobs()
    for text in ("/continue", "/next", "/rest", "/choose a 一句话"):
        portal._queue_memory_input("player", "game", text, text)
    portal._queue_memory_input("player", "game", "speech", "我喜欢慢慢认识人。")
    assert portal.memory_jobs.inputs == ["我喜欢慢慢认识人。"]


def test_mem0_embedded_store_is_persistent_and_user_scoped_without_model_calls(tmp_path: Path) -> None:
    config = replace(HarnessConfig.load(ROOT / "config/online.json"), local_api_key="offline-key")
    memory = Mem0PlayerMemory(config, tmp_path / "memory")
    try:
        memory._memory.embedding_model.embed = lambda _text, _action=None: [0.1] * 1024
        memory._memory.add("player prefers slower pacing", user_id="player-a", infer=False)
        assert len(memory.list_memories("player-a")) == 1
        assert memory.list_memories("player-b") == []
    finally:
        memory.close()
    reopened = Mem0PlayerMemory(config, tmp_path / "memory")
    try:
        assert len(reopened.list_memories("player-a")) == 1
        reopened.clear("player-a")
        assert reopened.list_memories("player-a") == []
    finally:
        reopened.close()
