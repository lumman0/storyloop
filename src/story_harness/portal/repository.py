"""SQLite player accounts, bearer sessions, and save ownership."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class SaveRecord:
    game_id: str
    player_id: str
    catalog_id: str
    package_id: str
    package_version: str
    package_hash: str
    created_at: int


class PlayerRepository(Protocol):
    def register(self, username: str, password: str) -> str: ...
    def authenticate(self, username: str, password: str) -> str: ...
    def issue_token(self, player_id: str) -> str: ...
    def resolve_token(self, token: str) -> str: ...
    def revoke_token(self, token: str) -> None: ...
    def create_save(self, player_id: str, catalog_id: str, game_id: str,
                    package_id: str, package_version: str, package_hash: str) -> SaveRecord: ...
    def get_save(self, player_id: str, game_id: str) -> SaveRecord: ...
    def list_saves(self, player_id: str) -> tuple[SaveRecord, ...]: ...
    def get_turn_response(self, game_id: str, request_id: str, text: str) -> dict | None: ...
    def latest_turn_response(self, game_id: str) -> dict | None: ...
    def store_turn_response(self, game_id: str, request_id: str, text: str,
                            response: dict) -> None: ...


class SQLitePlayerRepository:
    def __init__(self, path: str) -> None:
        self.path = path
        with closing(self._connect()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS player_accounts (
                    player_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS player_sessions (
                    token_hash BLOB PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS player_saves (
                    game_id TEXT PRIMARY KEY,
                    player_id TEXT NOT NULL,
                    catalog_id TEXT NOT NULL,
                    package_id TEXT NOT NULL,
                    package_version TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS player_saves_owner
                    ON player_saves(player_id, created_at);
                CREATE TABLE IF NOT EXISTS portal_turns (
                    game_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    input_hash BLOB NOT NULL,
                    response_json TEXT NOT NULL,
                    PRIMARY KEY (game_id, request_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _username(value: str) -> str:
        name = value.strip().casefold() if isinstance(value, str) else ""
        if not re.fullmatch(r"[\w.-]{2,32}", name, flags=re.UNICODE):
            raise ValueError("username must contain 2–32 letters, digits, dots, dashes, or underscores")
        return name

    @staticmethod
    def _password(value: str) -> str:
        if not isinstance(value, str) or len(value) < 8 or len(value) > 256:
            raise ValueError("password must contain 8–256 characters")
        return value

    def register(self, username: str, password: str) -> str:
        name = self._username(username)
        secret = self._password(password)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 310_000)
        player_id = uuid4().hex
        with closing(self._connect()) as db:
            try:
                db.execute("INSERT INTO player_accounts VALUES (?, ?, ?, ?, ?)",
                           (player_id, name, salt, digest, int(time.time())))
            except sqlite3.IntegrityError as error:
                raise ValueError("username already exists") from error
        return player_id

    def authenticate(self, username: str, password: str) -> str:
        name = self._username(username)
        secret = self._password(password)
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM player_accounts WHERE username = ?", (name,)).fetchone()
        if row is None:
            raise PermissionError("invalid username or password")
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), row["password_salt"], 310_000)
        if not hmac.compare_digest(digest, row["password_hash"]):
            raise PermissionError("invalid username or password")
        return row["player_id"]

    def issue_token(self, player_id: str) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).digest()
        with closing(self._connect()) as db:
            db.execute("INSERT INTO player_sessions VALUES (?, ?, ?)",
                       (token_hash, player_id, int(time.time()) + 7 * 24 * 3600))
        return token

    def resolve_token(self, token: str) -> str:
        if not isinstance(token, str) or not token:
            raise PermissionError("login required")
        with closing(self._connect()) as db:
            row = db.execute("SELECT player_id, expires_at FROM player_sessions WHERE token_hash = ?",
                             (hashlib.sha256(token.encode()).digest(),)).fetchone()
        if row is None or row["expires_at"] <= int(time.time()):
            raise PermissionError("login required")
        return row["player_id"]

    def revoke_token(self, token: str) -> None:
        with closing(self._connect()) as db:
            db.execute("DELETE FROM player_sessions WHERE token_hash = ?",
                       (hashlib.sha256(token.encode()).digest(),))

    def create_save(self, player_id: str, catalog_id: str, game_id: str,
                    package_id: str, package_version: str, package_hash: str) -> SaveRecord:
        record = SaveRecord(game_id, player_id, catalog_id, package_id, package_version,
                            package_hash, int(time.time()))
        with closing(self._connect()) as db:
            db.execute("INSERT INTO player_saves VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (record.game_id, record.player_id, record.catalog_id, record.package_id,
                        record.package_version, record.package_hash, record.created_at))
        return record

    def get_save(self, player_id: str, game_id: str) -> SaveRecord:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM player_saves WHERE player_id = ? AND game_id = ?",
                             (player_id, game_id)).fetchone()
        if row is None:
            raise KeyError("save not found")
        return SaveRecord(row["game_id"], row["player_id"], row["catalog_id"],
                          row["package_id"], row["package_version"], row["package_hash"],
                          row["created_at"])

    def list_saves(self, player_id: str) -> tuple[SaveRecord, ...]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT * FROM player_saves WHERE player_id = ? ORDER BY created_at DESC, game_id",
                              (player_id,)).fetchall()
        return tuple(SaveRecord(row["game_id"], row["player_id"], row["catalog_id"],
                                row["package_id"], row["package_version"], row["package_hash"],
                                row["created_at"]) for row in rows)

    def get_turn_response(self, game_id: str, request_id: str, text: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT input_hash, response_json FROM portal_turns WHERE game_id = ? AND request_id = ?",
                             (game_id, request_id)).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["input_hash"], hashlib.sha256(text.encode()).digest()):
            raise ValueError("request ID already belongs to different input")
        return json.loads(row["response_json"])

    def latest_turn_response(self, game_id: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT response_json FROM portal_turns WHERE game_id = ? ORDER BY rowid DESC LIMIT 1",
                             (game_id,)).fetchone()
        return json.loads(row["response_json"]) if row is not None else None

    def store_turn_response(self, game_id: str, request_id: str, text: str,
                            response: dict) -> None:
        with closing(self._connect()) as db:
            db.execute("INSERT INTO portal_turns VALUES (?, ?, ?, ?)",
                       (game_id, request_id, hashlib.sha256(text.encode()).digest(),
                        json.dumps(response, ensure_ascii=False)))
