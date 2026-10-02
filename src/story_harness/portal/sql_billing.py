"""Atomic credit balance, usage ledger, and turn receipt persistence."""

from __future__ import annotations

import hashlib
import json
import time

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from story_harness.core.billing import BillingPolicy, ModelUsage, MILLI_POINTS
from story_harness.portal.sql_repository import SQLPlayerRepository


def _points(milli_points: int) -> str:
    sign = "-" if milli_points < 0 else ""
    whole, fractional = divmod(abs(milli_points), MILLI_POINTS)
    return f"{sign}{whole}.{fractional:03d}"


class SQLBillingRepository:
    def __init__(self, engine: Engine, policy: BillingPolicy,
                 players: SQLPlayerRepository) -> None:
        self.engine = engine
        self.policy = policy
        self.players = players

    def ensure_wallet(self, player_id: str) -> None:
        opening = self.policy.welcome_points * MILLI_POINTS
        with self.engine.begin() as db:
            inserted = db.execute(text("""INSERT INTO credit_wallets
                (player_id,balance_milli_points) VALUES (:player_id,:balance)
                ON CONFLICT (player_id) DO NOTHING RETURNING player_id"""),
                {"player_id": player_id, "balance": opening}).first()
            if inserted is not None:
                db.execute(text("""INSERT INTO credit_ledger
                    (entry_id,player_id,kind,game_id,request_id,delta_milli_points,
                     usage_cost_milli_points,balance_after_milli_points,pricing_version,
                     usage_json,created_order)
                    VALUES (:entry_id,:player_id,'welcome',NULL,NULL,:delta,0,:balance,
                            :pricing_version,'[]',:created_order)"""),
                    {"entry_id": f"welcome:{player_id}", "player_id": player_id,
                     "delta": opening, "balance": opening,
                     "pricing_version": self.policy.pricing_version,
                     "created_order": time.time_ns()})

    def wallet(self, player_id: str) -> dict:
        self.ensure_wallet(player_id)
        with self.engine.connect() as db:
            balance = db.execute(text("""SELECT balance_milli_points FROM credit_wallets
                WHERE player_id=:player_id"""), {"player_id": player_id}).scalar_one()
        return {"balance_milli_points": balance, "balance_points": _points(balance),
                "welcome_points": self.policy.welcome_points,
                "points_per_rmb": self.policy.points_per_rmb}

    def require_credit(self, player_id: str) -> None:
        if self.wallet(player_id)["balance_milli_points"] <= 0:
            raise ValueError("积分已用完，暂时无法开始新回合")

    def ledger(self, player_id: str, limit: int = 30) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("ledger limit must be between 1 and 100")
        self.ensure_wallet(player_id)
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT entry_id,kind,game_id,request_id,
                delta_milli_points,usage_cost_milli_points,balance_after_milli_points,
                pricing_version,usage_json,created_order FROM credit_ledger
                WHERE player_id=:player_id ORDER BY created_order DESC,entry_id DESC
                LIMIT :limit"""), {"player_id": player_id, "limit": limit}).mappings().all()
        return [
            {"entry_id": row["entry_id"], "kind": row["kind"], "game_id": row["game_id"],
             "request_id": row["request_id"], "delta_milli_points": row["delta_milli_points"],
             "delta_points": _points(row["delta_milli_points"]),
             "usage_cost_milli_points": row["usage_cost_milli_points"],
             "balance_after_points": _points(row["balance_after_milli_points"]),
             "pricing_version": row["pricing_version"],
             "usage": json.loads(row["usage_json"]), "created_order": row["created_order"]}
            for row in rows
        ]

    def settle_turn(self, player_id: str, game_id: str, request_id: str,
                    player_text: str, response: dict, usage: list[ModelUsage]) -> dict:
        """Store the player response and one debit in the same SQL transaction."""
        self.ensure_wallet(player_id)
        usage_cost = self.policy.price_milli_points(usage)
        raw_usage = [item.to_dict() for item in usage]
        entry_id = f"turn:{game_id}:{request_id}"
        try:
            with self.engine.begin() as db:
                if self.engine.dialect.name == "sqlite":
                    db.exec_driver_sql("BEGIN IMMEDIATE")
                lock = " FOR UPDATE" if self.engine.dialect.name == "postgresql" else ""
                balance = db.execute(text("""SELECT balance_milli_points FROM credit_wallets
                    WHERE player_id=:player_id""" + lock),
                    {"player_id": player_id}).scalar_one()
                charged = min(balance, usage_cost)
                after = balance - charged
                billed = {**response, "billing": {
                    "charged_milli_points": charged, "charged_points": _points(charged),
                    "usage_cost_milli_points": usage_cost,
                    "balance_milli_points": after, "balance_points": _points(after),
                    "input_tokens": sum(item.input_tokens for item in usage),
                    "output_tokens": sum(item.output_tokens for item in usage),
                    "model_calls": len(usage),
                }}
                db.execute(text("""INSERT INTO portal_turns
                    (game_id,request_id,input_hash,input_text,response_json,created_order)
                    VALUES (:game_id,:request_id,:input_hash,:input_text,:response_json,:created_order)"""),
                    {"game_id": game_id, "request_id": request_id,
                     "input_hash": hashlib.sha256(player_text.encode()).digest(),
                     "input_text": player_text,
                     "response_json": json.dumps(billed, ensure_ascii=False),
                     "created_order": time.time_ns()})
                db.execute(text("""UPDATE credit_wallets SET balance_milli_points=:balance
                    WHERE player_id=:player_id"""), {"balance": after, "player_id": player_id})
                db.execute(text("""INSERT INTO credit_ledger
                    (entry_id,player_id,kind,game_id,request_id,delta_milli_points,
                     usage_cost_milli_points,balance_after_milli_points,pricing_version,
                     usage_json,created_order)
                    VALUES (:entry_id,:player_id,'turn',:game_id,:request_id,:delta,
                            :usage_cost,:balance,:pricing_version,:usage_json,:created_order)"""),
                    {"entry_id": entry_id, "player_id": player_id, "game_id": game_id,
                     "request_id": request_id, "delta": -charged, "usage_cost": usage_cost,
                     "balance": after, "pricing_version": self.policy.pricing_version,
                     "usage_json": json.dumps(raw_usage, ensure_ascii=False),
                     "created_order": time.time_ns()})
            return billed
        except IntegrityError as error:
            cached = self.players.get_turn_response(game_id, request_id, player_text)
            if cached is None:
                raise error
            return cached
