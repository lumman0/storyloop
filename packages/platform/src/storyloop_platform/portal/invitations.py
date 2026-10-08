"""One-time registration invitations with an explicit issuance policy."""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Protocol
from uuid import uuid4

from sqlalchemy import Engine, text

from storyloop_platform.portal.access import AccessService, audit


INVITE_LIFETIME_SECONDS = 30 * 24 * 3600
MAX_ISSUE_COUNT = 20


class InvitationIssuancePolicy(Protocol):
    def require(self, player_id: str) -> None: ...


class AdministratorIssuancePolicy:
    """Private-test policy; later policies can use a player's completed turns."""

    def __init__(self, access: AccessService) -> None:
        self.access = access

    def require(self, player_id: str) -> None:
        self.access.require(player_id, "invites.issue")


class InvitationService:
    def __init__(self, engine: Engine, access: AccessService,
                 issuance_policy: InvitationIssuancePolicy | None = None) -> None:
        self.engine = engine
        self.access = access
        self.issuance_policy = issuance_policy or AdministratorIssuancePolicy(access)

    def issue(self, actor_id: str, count: int = 1) -> dict:
        self.issuance_policy.require(actor_id)
        if type(count) is not int or not 1 <= count <= MAX_ISSUE_COUNT:
            raise ValueError(f"invite count must be between 1 and {MAX_ISSUE_COUNT}")
        now = int(time.time())
        expiry = now + INVITE_LIFETIME_SECONDS
        codes = [secrets.token_urlsafe(24) for _ in range(count)]
        identifiers = [hashlib.sha256(code.encode()).digest() for code in codes]
        with self.engine.begin() as db:
            for code_hash in identifiers:
                db.execute(text("""INSERT INTO signup_invites
                    (code_hash,expires_at,issued_by,created_at)
                    VALUES (:code_hash,:expires_at,:issued_by,:created_at)"""),
                    {"code_hash": code_hash, "expires_at": expiry,
                     "issued_by": actor_id, "created_at": now})
            audit(db, actor_id, "invitation.issue", "invitation_batch", uuid4().hex,
                  {"count": count, "expires_at": expiry,
                   "invitation_ids": [value.hex() for value in identifiers]})
        return {"codes": codes, "expires_at": expiry}

    def list_invitations(self, actor_id: str) -> list[dict]:
        self.access.require(actor_id, "invites.read")
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT i.*,issuer.username AS issuer_name,
                recipient.username AS used_name FROM signup_invites i
                LEFT JOIN player_accounts issuer ON issuer.player_id=i.issued_by
                LEFT JOIN player_accounts recipient ON recipient.player_id=i.used_by
                ORDER BY i.expires_at DESC,i.code_hash DESC LIMIT 100""")).mappings().all()
        now = int(time.time())
        return [{"id": bytes(row["code_hash"]).hex(),
                 "issuer_name": row["issuer_name"], "issued_by": row["issued_by"],
                 "used_name": row["used_name"], "created_at": row["created_at"],
                 "expires_at": row["expires_at"], "used_at": row["used_at"],
                 "revoked_at": row["revoked_at"],
                 "status": ("used" if row["used_by"] is not None else
                            "revoked" if row["revoked_at"] is not None else
                            "expired" if row["expires_at"] <= now else "available")}
                for row in rows]

    def revoke(self, actor_id: str, invitation_id: str) -> dict:
        self.access.require(actor_id, "invites.revoke")
        try:
            code_hash = bytes.fromhex(invitation_id)
        except ValueError as error:
            raise ValueError("invalid invitation ID") from error
        if len(code_hash) != 32:
            raise ValueError("invalid invitation ID")
        now = int(time.time())
        with self.engine.begin() as db:
            result = db.execute(text("""UPDATE signup_invites
                SET revoked_at=:now,revoked_by=:actor WHERE code_hash=:hash
                AND used_by IS NULL AND revoked_at IS NULL AND expires_at>:now"""),
                {"now": now, "actor": actor_id, "hash": code_hash})
            if result.rowcount != 1:
                raise ValueError("invitation is no longer available")
            audit(db, actor_id, "invitation.revoke", "invitation", invitation_id)
        return {"id": invitation_id, "status": "revoked", "revoked_at": now}
