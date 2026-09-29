"""One migration and profile parity smoke test for the two launch modes."""

from __future__ import annotations

import tempfile
import unittest
import sqlite3
import hashlib
import json
from contextlib import closing
from pathlib import Path

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.portal.sql_repository import SQLPlayerRepository


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentProfileSmokeTest(unittest.TestCase):
    def test_existing_sqlite_save_and_player_survive_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.sqlite3")
            salt = b"legacy-salt-1234"
            digest = hashlib.pbkdf2_hmac("sha256", b"password-123", salt, 310_000)
            player_id = "legacy-player-id"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript("""
                    CREATE TABLE games (game_id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                                        tick INTEGER NOT NULL, data TEXT NOT NULL);
                    CREATE TABLE player_accounts (player_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                                                  password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                                                  created_at INTEGER NOT NULL);
                    CREATE TABLE player_saves (game_id TEXT PRIMARY KEY, player_id TEXT NOT NULL,
                                               catalog_id TEXT NOT NULL, package_id TEXT NOT NULL,
                                               package_version TEXT NOT NULL, package_hash TEXT NOT NULL,
                                               created_at INTEGER NOT NULL);
                    CREATE TABLE portal_turns (game_id TEXT NOT NULL, request_id TEXT NOT NULL,
                                               input_hash BLOB NOT NULL, response_json TEXT NOT NULL,
                                               PRIMARY KEY (game_id, request_id));
                """)
                db.execute("INSERT INTO games VALUES ('saved-game',0,0,'{}')")
                db.execute("INSERT INTO player_accounts VALUES (?,?,?,?,?)",
                           (player_id, "legacy-player", salt, digest, 1))
                db.execute("INSERT INTO player_saves VALUES (?,?,?,?,?,?,?)",
                           ("saved-game", player_id, "npc-chat", "harbor-freeform", "1", "fingerprint", 1))
                db.execute("INSERT INTO portal_turns VALUES (?,?,?,?)",
                           ("saved-game", "legacy-request", hashlib.sha256(b"hi").digest(),
                            '{"state_version": 0}'))

            config = HarnessConfig.load(ROOT / "config" / "local.json")
            engine = config.create_database(path)
            try:
                store = config.create_store(engine=engine)
                accounts = SQLPlayerRepository(engine)
                self.assertEqual(store.load("saved-game").game_id, "saved-game")
                self.assertEqual(accounts.authenticate("legacy-player", "password-123"), player_id)
                self.assertEqual(accounts.get_save(player_id, "saved-game").catalog_id, "npc-chat")
                self.assertEqual(accounts.latest_turn_response("saved-game"), {"state_version": 0})
                token = accounts.issue_token(player_id)
                self.assertEqual(accounts.resolve_token(token), player_id)
                accounts.revoke_token(token)
                with self.assertRaises(PermissionError):
                    accounts.resolve_token(token)
            finally:
                engine.dispose()

    def test_online_profile_requires_explicit_postgres_and_host(self) -> None:
        for profile in ("local", "online"):
            self.assertEqual(
                json.loads((ROOT / "config" / f"{profile}.json").read_text(encoding="utf-8")),
                json.loads((ROOT / "src" / "story_harness" / "defaults" /
                            f"{profile}.json").read_text(encoding="utf-8")),
            )
        config = HarnessConfig.load(ROOT / "config" / "online.json")
        with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
            config.database_url(env={})
        with self.assertRaisesRegex(ValueError, "postgresql\\+psycopg"):
            config.database_url(env={"DATABASE_URL": "sqlite:///wrong.db"})
        with self.assertRaisesRegex(ValueError, "STORY_ALLOWED_HOSTS"):
            config.allowed_hosts(env={})
        self.assertEqual(config.allowed_hosts(env={"STORY_ALLOWED_HOSTS": "game.example.com"}),
                         ("game.example.com",))
        self.assertEqual(config.allowed_origins(env={"STORY_ALLOWED_ORIGINS": "https://game.example.com"}),
                         ("https://game.example.com",))


if __name__ == "__main__":
    unittest.main()
