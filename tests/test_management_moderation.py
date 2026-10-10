"""Authorization and immutable-version publication boundaries."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app
from storyloop_platform.config import load_settings
from storyloop_platform.bootstrap import build_portal


ROOT = Path(__file__).resolve().parents[1]


def _archive() -> bytes:
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as bundle:
        for file in (ROOT / "examples/freeform").glob("*.json"):
            bundle.write(file, file.name)
    return result.getvalue()


def test_review_roles_approval_public_catalog_and_account_revocation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("STORY_UPLOAD_DIR", str(tmp_path / "uploads"))
    portal = build_portal(ROOT / "examples/catalog.json", load_settings(ROOT / "config/local.json"),
                          str(tmp_path / "portal.sqlite3"),
                          prologue_generator=lambda *_: "固定开场。\n\n现在可以开始故事。")
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        author = portal.register("author", "password-123")
        reviewer = portal.register("reviewer", "password-123")
        reader = portal.register("reader", "password-123")
        admin = portal.register("administrator", "password-123")
        portal.access.bootstrap_admin("administrator")
        with pytest.raises(ValueError, match="last administrator"):
            portal.access.set_role(admin["player_id"], admin["player_id"], "admin", False)
        portal.access.set_role(admin["player_id"], reviewer["player_id"], "reviewer", True)
        item = portal.upload_scenario(author["token"], "送审剧本", "简介", _archive())
        submission = portal.submit_scenario(author["token"], item["id"])
        assert submission["status"] == "pending"
        assert item["id"] not in [game["id"] for game in portal.games(reader["token"])]
        headers = {"Authorization": f"Bearer {reader['token']}"}
        assert client.get("/v1/manage/submissions", headers=headers).status_code == 403
        reviewer_headers = {"Authorization": f"Bearer {reviewer['token']}"}
        assert client.get("/v1/manage/submissions", headers=reviewer_headers).status_code == 200
        detail = client.get(f"/v1/manage/submissions/{submission['submission_id']}",
                            headers=reviewer_headers).json()
        assert detail["package_hash"] == submission["package_hash"]
        assert detail["manifest"] and detail["worldbook"]
        result = client.post(f"/v1/manage/submissions/{submission['submission_id']}/decision",
                             headers=reviewer_headers, json={"decision": "approved", "reason": ""})
        assert result.status_code == 200, result.text
        assert item["id"] in [game["id"] for game in portal.games(reader["token"])]
        assert portal.gameplay.game_access.listing_for(reader["player_id"], item["id"]).fingerprint == submission["package_hash"]
        second = client.post(f"/v1/manage/submissions/{submission['submission_id']}/decision",
                             headers=reviewer_headers,
                             json={"decision": "rejected", "reason": "conflict"})
        assert second.status_code == 400
        portal.admin_release_state(admin["token"], item["id"], "retired", "")
        assert item["id"] not in [game["id"] for game in portal.games(reader["token"])]
        assert portal.gameplay.game_access.listing_for(reader["player_id"], item["id"],
                                   submission["package_hash"]).fingerprint == submission["package_hash"]
        portal.admin_release_state(admin["token"], item["id"], "blocked", "policy violation")
        with pytest.raises((KeyError, PermissionError)):
            portal.gameplay.game_access.listing_for(reader["player_id"], item["id"], submission["package_hash"])
        portal.admin_set_status(admin["token"], reviewer["player_id"], "suspended")
        assert client.get("/v1/manage/submissions", headers=reviewer_headers).status_code == 401


def test_rejected_version_can_be_replaced_but_private_draft_cannot_disappear(tmp_path: Path,
                                                                               monkeypatch) -> None:
    monkeypatch.setenv("STORY_UPLOAD_DIR", str(tmp_path / "uploads"))
    portal = build_portal(ROOT / "examples/catalog.json", load_settings(ROOT / "config/local.json"),
                          str(tmp_path / "portal.sqlite3"),
                          prologue_generator=lambda *_: "固定开场。\n\n现在可以开始故事。")
    try:
        author = portal.register("author", "password-123")
        admin = portal.register("administrator", "password-123")
        reviewer = portal.register("reviewer", "password-123")
        portal.access.bootstrap_admin("administrator")
        portal.access.set_role(admin["player_id"], reviewer["player_id"], "reviewer", True)
        item = portal.upload_scenario(author["token"], "送审剧本", "简介", _archive())
        first = portal.submit_scenario(author["token"], item["id"])
        with pytest.raises(ValueError):
            portal.delete_scenario_draft(author["token"], item["id"])
        with pytest.raises(ValueError):
            portal.submit_scenario(author["token"], item["id"])
        with pytest.raises(PermissionError):
            portal.review_decide(author["token"], first["submission_id"], "approved")
        portal.review_decide(reviewer["token"], first["submission_id"], "rejected", "请修改开场")
        revision = portal.upload_scenario_version(author["token"], item["id"],
                                                   "送审剧本", "修改后", _archive())
        assert revision["version_id"] != item["version_id"]
        second = portal.submit_scenario(author["token"], item["id"])
        assert second["version_id"] == revision["version_id"]
        assert portal.withdraw_submission(author["token"], second["submission_id"])["status"] == "withdrawn"
        with pytest.raises(ValueError):
            portal.review_decide(reviewer["token"], second["submission_id"], "approved")
    finally:
        portal.close()
