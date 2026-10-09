"""Administrator-issued one-time invitations stay private and accountable."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app
from storyloop_platform.portal.service import PlayerPortal


ROOT = Path(__file__).resolve().parents[1]


def test_admin_can_issue_track_and_revoke_registration_invites(tmp_path: Path) -> None:
    portal = PlayerPortal(ROOT / "config/games.example.json", ROOT / "config/local.json",
                          str(tmp_path / "portal.sqlite3"))
    with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
        admin = portal.register("administrator", "password-123")
        player = portal.register("ordinary", "password-123")
        portal.access.bootstrap_admin("administrator")
        admin_headers = {"Authorization": f"Bearer {admin['token']}"}
        player_headers = {"Authorization": f"Bearer {player['token']}"}

        assert client.post("/v1/manage/invites", json={"count": 1},
                           headers=player_headers).status_code == 403
        assert client.get("/v1/manage/invites", headers=player_headers).status_code == 403

        response = client.post("/v1/manage/invites", json={"count": 2},
                               headers=admin_headers)
        assert response.status_code == 201, response.text
        codes = response.json()["codes"]
        assert len(codes) == 2 and codes[0] != codes[1]

        listing = client.get("/v1/manage/invites", headers=admin_headers)
        assert listing.status_code == 200
        invitations = listing.json()["invites"]
        assert len(invitations) == 2
        assert all(item["status"] == "available" for item in invitations)
        assert all(item["issuer_name"] == "administrator" for item in invitations)
        assert all(code not in json.dumps(invitations) for code in codes)

        portal.accounts.register("friend", "password-123", codes[0], require_invite=True)
        with pytest.raises(ValueError, match="invite"):
            portal.accounts.register("second-friend", "password-123", codes[0],
                                     require_invite=True)
        listing = client.get("/v1/manage/invites", headers=admin_headers).json()["invites"]
        assert {item["status"] for item in listing} == {"available", "used"}
        unused = next(item for item in listing if item["status"] == "available")
        assert client.post(f"/v1/manage/invites/{unused['id']}/revoke",
                           headers=player_headers).status_code == 403
        used = next(item for item in listing if item["status"] == "used")
        assert client.post(f"/v1/manage/invites/{used['id']}/revoke",
                           headers=admin_headers).status_code == 400
        revoked = client.post(f"/v1/manage/invites/{unused['id']}/revoke",
                              headers=admin_headers)
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        with pytest.raises(ValueError, match="invite"):
            portal.accounts.register("third-friend", "password-123", codes[1],
                                     require_invite=True)
        assert any(item["action"] == "invitation.issue" for item in portal.admin_audit(admin["token"]))
