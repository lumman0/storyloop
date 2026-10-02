import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from story_harness.adapters.sql_database import open_database, sqlite_url, upgrade_database
from story_harness.portal.service import PlayerPortal
from story_harness.portal.sql_repository import SQLPlayerRepository


ROOT = Path(__file__).resolve().parents[1]


class SignupInviteTests(unittest.TestCase):
    def test_online_signup_requires_one_time_invite(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }):
            portal = PlayerPortal(ROOT / "config" / "games.example.json",
                                  ROOT / "config" / "local.json", str(Path(temp) / "game.sqlite3"))
            try:
                portal.config = replace(portal.config, profile="online")
                with self.assertRaisesRegex(ValueError, "invite"):
                    portal.register("no-invite", "password-123")
                invite = portal.accounts.issue_signup_invite()
                first = portal.register("invited-one", "password-123", invite)
                self.assertTrue(first["token"])
                with self.assertRaisesRegex(ValueError, "invite"):
                    portal.register("invited-two", "password-123", invite)
                with self.assertRaises(PermissionError):
                    portal.login("invited-two", "password-123")
            finally:
                portal.close()

    def test_local_registration_remains_open(self):
        with tempfile.TemporaryDirectory() as temp:
            url = sqlite_url(str(Path(temp) / "accounts.sqlite3"))
            upgrade_database(url)
            engine = open_database(url)
            try:
                account = SQLPlayerRepository(engine)
                self.assertTrue(account.register("local-user", "password-123"))
            finally:
                engine.dispose()
