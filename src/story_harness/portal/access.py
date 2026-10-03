"""Database-backed capabilities and append-only management audit."""

from __future__ import annotations

import json
import time
from uuid import uuid4

from sqlalchemy import Engine, text


ROLE_CAPABILITIES = {
    "reviewer": frozenset({"review.submissions", "review.decide"}),
    "admin": frozenset({"review.submissions", "review.decide", "users.read",
                        "users.manage", "releases.manage", "audit.read",
                        "invites.issue", "invites.read", "invites.revoke"}),
}


class AccessDenied(PermissionError):
    """Authenticated account lacks a management capability."""


def audit(db, actor_id: str, action: str, target_type: str, target_id: str,
          details: dict | None = None) -> None:
    db.execute(text("""INSERT INTO management_audit
        (event_id,actor_id,action,target_type,target_id,details_json,created_at)
        VALUES (:event_id,:actor_id,:action,:target_type,:target_id,:details,:created_at)"""),
        {"event_id": uuid4().hex, "actor_id": actor_id, "action": action,
         "target_type": target_type, "target_id": target_id,
         "details": json.dumps(details or {}, ensure_ascii=False), "created_at": int(time.time())})


class AccessService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def roles(self, player_id: str) -> tuple[str, ...]:
        with self.engine.connect() as db:
            return tuple(db.execute(text("SELECT role FROM player_roles WHERE player_id=:id ORDER BY role"),
                                    {"id": player_id}).scalars())

    def capabilities(self, player_id: str) -> tuple[str, ...]:
        return tuple(sorted(set().union(*(ROLE_CAPABILITIES[role]
                                         for role in self.roles(player_id)
                                         if role in ROLE_CAPABILITIES))))

    def require(self, player_id: str, capability: str) -> None:
        if capability not in self.capabilities(player_id):
            raise AccessDenied("insufficient permissions")

    def list_users(self, actor_id: str, limit: int = 100) -> list[dict]:
        self.require(actor_id, "users.read")
        limit = max(1, min(int(limit), 100))
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT player_id,username,status,created_at
                FROM player_accounts ORDER BY created_at DESC,player_id LIMIT :limit"""),
                {"limit": limit}).mappings().all()
        return [{**dict(row), "roles": list(self.roles(row["player_id"]))} for row in rows]

    def set_role(self, actor_id: str, target_id: str, role: str, enabled: bool) -> None:
        self.require(actor_id, "users.manage")
        if role not in ROLE_CAPABILITIES:
            raise ValueError("unknown role")
        with self.engine.begin() as db:
            target = db.execute(text("""UPDATE player_accounts SET player_id=player_id
                WHERE player_id=:id"""), {"id": target_id})
            if target.rowcount != 1:
                raise KeyError("user not found")
            if role == "admin" and not enabled:
                is_active_admin = db.execute(text("""SELECT 1 FROM player_roles r
                    JOIN player_accounts a ON a.player_id=r.player_id
                    WHERE r.player_id=:id AND r.role='admin' AND a.status='active'"""),
                    {"id": target_id}).first()
                count = db.execute(text("""SELECT COUNT(*) FROM player_roles r
                    JOIN player_accounts a ON a.player_id=r.player_id
                    WHERE r.role='admin' AND a.status='active'""")).scalar_one()
                if is_active_admin and count <= 1:
                    raise ValueError("cannot remove the last administrator")
            if enabled:
                result = db.execute(text("""INSERT INTO player_roles (player_id,role)
                    VALUES (:id,:role) ON CONFLICT (player_id,role) DO NOTHING"""),
                    {"id": target_id, "role": role})
            else:
                result = db.execute(text("DELETE FROM player_roles WHERE player_id=:id AND role=:role"),
                                    {"id": target_id, "role": role})
            if result.rowcount:
                audit(db, actor_id, "role.grant" if enabled else "role.revoke", "user", target_id,
                      {"role": role})

    def set_status(self, actor_id: str, target_id: str, status: str) -> None:
        self.require(actor_id, "users.manage")
        if status not in {"active", "suspended"}:
            raise ValueError("invalid account status")
        if target_id == actor_id and status == "suspended":
            raise ValueError("cannot suspend your own account")
        with self.engine.begin() as db:
            row = db.execute(text("SELECT status FROM player_accounts WHERE player_id=:id"),
                             {"id": target_id}).mappings().first()
            if row is None:
                raise KeyError("user not found")
            if status == "suspended" and db.execute(text("""SELECT 1 FROM player_roles
                WHERE player_id=:id AND role='admin'"""), {"id": target_id}).first():
                count = db.execute(text("""SELECT COUNT(*) FROM player_roles r
                    JOIN player_accounts a ON a.player_id=r.player_id
                    WHERE r.role='admin' AND a.status='active'""")).scalar_one()
                if count <= 1:
                    raise ValueError("cannot suspend the last active administrator")
            if row["status"] != status:
                db.execute(text("UPDATE player_accounts SET status=:status WHERE player_id=:id"),
                           {"id": target_id, "status": status})
                if status == "suspended":
                    db.execute(text("DELETE FROM player_sessions WHERE player_id=:id"),
                               {"id": target_id})
                audit(db, actor_id, "account.status", "user", target_id, {"status": status})

    def list_audit(self, actor_id: str, limit: int = 100) -> list[dict]:
        self.require(actor_id, "audit.read")
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT * FROM management_audit
                ORDER BY created_at DESC,event_id DESC LIMIT :limit"""),
                {"limit": max(1, min(int(limit), 100))}).mappings().all()
        return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]

    def bootstrap_admin(self, username: str) -> str:
        with self.engine.begin() as db:
            row = db.execute(text("""SELECT player_id FROM player_accounts
                WHERE username=:username AND status='active'"""),
                {"username": username.strip().casefold()}).mappings().first()
            if row is None:
                raise KeyError("active account not found")
            player_id = row["player_id"]
            db.execute(text("""INSERT INTO player_roles (player_id,role)
                VALUES (:id,'admin') ON CONFLICT (player_id,role) DO NOTHING"""),
                {"id": player_id})
            audit(db, "system:cli", "role.bootstrap", "user", player_id)
            return player_id
