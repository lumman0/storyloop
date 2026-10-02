import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text

from story_harness.adapters.sql_database import open_database, sqlite_url, upgrade_database
from story_harness.core.billing import BillingPolicy, ModelUsage, record_model_usage
from story_harness.portal.service import PlayerPortal
from story_harness.portal.sql_billing import SQLBillingRepository
from story_harness.portal.sql_repository import SQLPlayerRepository


class CreditWalletTests(unittest.TestCase):
    def test_resume_waits_for_inflight_turn_after_browser_reconnect(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }):
            portal = PlayerPortal(root / "config" / "games.example.json",
                                  root / "config" / "local.json",
                                  str(Path(temp) / "portal.sqlite3"))
            try:
                token = portal.register("reconnect-user", "password-123")["token"]
                game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
                entered = asyncio.Event()
                release = asyncio.Event()

                class SlowSession:
                    async def run_turn(self, game_id, text, turn_id, progress=None):
                        entered.set()
                        await release.wait()
                        return SimpleNamespace(narration="完成", segments=(),
                                               snapshot=portal.store.load(game_id))

                portal._react = lambda item, package: SlowSession()

                async def reconnect():
                    turn = asyncio.create_task(portal.turn(token, game_id, "你好", "reconnect-1"))
                    await entered.wait()
                    resumed = asyncio.create_task(portal.resume_save(token, game_id))
                    await asyncio.sleep(0.02)
                    self.assertFalse(resumed.done())
                    release.set()
                    await turn
                    return await resumed

                result = asyncio.run(reconnect())
                self.assertEqual(result["body"], "完成")
            finally:
                portal.close()

    def test_concurrent_saves_share_one_credit_gate(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }):
            portal = PlayerPortal(root / "config" / "games.example.json",
                                  root / "config" / "local.json",
                                  str(Path(temp) / "portal.sqlite3"))
            try:
                account = portal.register("parallel-user", "password-123")
                token = account["token"]
                game_ids = [asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]
                            for _ in range(2)]
                with portal.engine.begin() as db:
                    db.execute(text("UPDATE credit_wallets SET balance_milli_points=100 "
                                    "WHERE player_id=:player_id"),
                               {"player_id": account["player_id"]})

                class FakeSession:
                    calls = 0

                    async def run_turn(self, game_id, text, turn_id, progress=None):
                        self.calls += 1
                        await asyncio.sleep(0.02)
                        record_model_usage("qwen3.8-flash", "npc_selection", SimpleNamespace(
                            input_tokens=1000, output_tokens=500,
                            metadata=SimpleNamespace(prompt_tokens_details={"cached_tokens": 200}),
                        ))
                        return SimpleNamespace(narration="你好", segments=(),
                                               snapshot=portal.store.load(game_id))

                session = FakeSession()
                portal._react = lambda item, package: session

                async def submit_both():
                    return await asyncio.gather(
                        *(portal.turn(token, game_id, "你好", f"request-{index}")
                          for index, game_id in enumerate(game_ids)),
                        return_exceptions=True,
                    )

                results = asyncio.run(submit_both())
                self.assertEqual(session.calls, 1)
                self.assertEqual(sum(isinstance(result, ValueError) for result in results), 1)
                self.assertEqual(portal.wallet(token)["balance_points"], "0.000")
            finally:
                portal.close()

    def test_welcome_grant_actual_usage_and_retry_are_atomic(self):
        with tempfile.TemporaryDirectory() as temp:
            url = sqlite_url(str(Path(temp) / "wallet.sqlite3"))
            upgrade_database(url)
            engine = open_database(url)
            try:
                players = SQLPlayerRepository(engine)
                policy = BillingPolicy.from_dict({
                    "welcome_points": 500, "points_per_rmb": 50,
                    "pricing_version": "test-1",
                    "models": {"flash": {"input_rmb_per_million": "0.8",
                                         "output_rmb_per_million": "2.7",
                                         "cached_input_rmb_per_million": "0.1"}},
                }, {"selection": "flash"})
                billing = SQLBillingRepository(engine, policy, players)
                player = players.register("wallet-user", "password-123")
                billing.ensure_wallet(player)
                billing.ensure_wallet(player)
                self.assertEqual(billing.wallet(player)["balance_points"], "500.000")
                self.assertEqual(len(billing.ledger(player)), 1)
                response = {"body": "你好", "game_id": "game"}
                usage = [ModelUsage("flash", "selection", 1000, 500, 200)]
                first = billing.settle_turn(player, "game", "request-1", "你好", response, usage)
                self.assertEqual(first["billing"]["charged_points"], "0.101")
                self.assertEqual(first["billing"]["balance_points"], "499.899")
                replay = billing.settle_turn(player, "game", "request-1", "你好", response, usage)
                self.assertEqual(replay, first)
                self.assertEqual(billing.wallet(player)["balance_points"], "499.899")
                self.assertEqual(len(billing.ledger(player)), 2)
                with self.assertRaises(ValueError):
                    billing.settle_turn(player, "game", "request-1", "别的话", response, usage)
            finally:
                engine.dispose()

    def test_portal_charges_only_completed_turn_and_retry_is_free(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
            "LANGFUSE_SECRET_KEY": "",
        }):
            portal = PlayerPortal(root / "config" / "games.example.json",
                                  root / "config" / "local.json",
                                  str(Path(temp) / "portal.sqlite3"))
            try:
                token = portal.register("meter-user", "password-123")["token"]
                game_id = asyncio.run(portal.create_save(token, "npc-chat"))["game_id"]

                class FakeSession:
                    calls = 0

                    async def run_turn(self, game_id, text, turn_id, progress=None):
                        self.calls += 1
                        if text == "失败":
                            raise RuntimeError("provider unavailable")
                        record_model_usage("qwen3.8-flash", "npc_selection", SimpleNamespace(
                            input_tokens=1000, output_tokens=500,
                            metadata=SimpleNamespace(prompt_tokens_details={"cached_tokens": 200}),
                        ))
                        return SimpleNamespace(narration="你好", segments=(),
                                               snapshot=portal.store.load(game_id))

                session = FakeSession()
                portal._react = lambda item, package: session
                first = asyncio.run(portal.turn(token, game_id, "你好", "one"))
                self.assertEqual(first["billing"]["charged_points"], "0.101")
                self.assertEqual(portal.wallet(token)["balance_points"], "499.899")
                again = asyncio.run(portal.turn(token, game_id, "你好", "one"))
                self.assertEqual(again, first)
                self.assertEqual(session.calls, 1)
                with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                    asyncio.run(portal.turn(token, game_id, "失败", "two"))
                self.assertEqual(portal.wallet(token)["balance_points"], "499.899")
                self.assertEqual(len(portal.credit_ledger(token)), 2)
            finally:
                portal.close()
