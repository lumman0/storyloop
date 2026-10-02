"""Durable, user-scoped batches for optional profile extraction."""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import Engine, text


BATCH_SIZE = 6
MIN_INTERVAL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class MemoryBatch:
    player_id: str
    items: tuple[tuple[str, str, str], ...]


class SQLPlayerMemoryJobs:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def enabled(self, player_id: str) -> bool:
        with self.engine.connect() as db:
            result = db.execute(text("SELECT enabled FROM player_memory_settings "
                                     "WHERE player_id=:player_id"),
                                {"player_id": player_id}).scalar_one_or_none()
        return bool(result)

    def set_enabled(self, player_id: str, enabled: bool) -> None:
        with self.engine.begin() as db:
            db.execute(text("""INSERT INTO player_memory_settings
                (player_id,enabled,last_generated_at) VALUES (:player_id,:enabled,0)
                ON CONFLICT (player_id) DO UPDATE SET enabled=:enabled"""),
                {"player_id": player_id, "enabled": enabled})
            if not enabled:
                db.execute(text("DELETE FROM player_memory_inputs WHERE player_id=:player_id"),
                           {"player_id": player_id})

    def enqueue(self, player_id: str, game_id: str, request_id: str, player_text: str) -> bool:
        content = player_text.strip()
        if len(content) < 12 or content.startswith("/"):
            return False
        now = int(time.time())
        with self.engine.begin() as db:
            result = db.execute(text("""INSERT INTO player_memory_inputs
                (game_id,request_id,player_id,input_text,status,attempt_count,available_at,created_at)
                SELECT :game_id,:request_id,:player_id,:input_text,'pending',0,:now,:now
                WHERE EXISTS (SELECT 1 FROM player_memory_settings
                              WHERE player_id=:player_id AND enabled=TRUE)
                ON CONFLICT (game_id,request_id) DO NOTHING"""),
                {"game_id": game_id, "request_id": request_id, "player_id": player_id,
                 "input_text": content[:2000], "now": now})
        return result.rowcount == 1

    def claim(self) -> MemoryBatch | None:
        now = int(time.time())
        with self.engine.begin() as db:
            candidates = db.execute(text("""SELECT player_id FROM player_memory_settings
                WHERE enabled=TRUE AND last_generated_at<=:oldest
                ORDER BY last_generated_at,player_id"""),
                {"oldest": now - MIN_INTERVAL_SECONDS}).scalars().all()
            for player_id in candidates:
                rows = db.execute(text("""SELECT game_id,request_id,input_text
                    FROM player_memory_inputs
                    WHERE player_id=:player_id AND attempt_count<3
                      AND (status='pending' OR (status='processing' AND available_at<=:now))
                      AND available_at<=:now
                    ORDER BY created_at,game_id,request_id LIMIT :limit"""),
                    {"player_id": player_id, "now": now, "limit": BATCH_SIZE}).mappings().all()
                if len(rows) < BATCH_SIZE:
                    continue
                items = tuple((row["game_id"], row["request_id"], row["input_text"])
                              for row in rows)
                for game_id, request_id, _ in items:
                    db.execute(text("""UPDATE player_memory_inputs
                        SET status='processing',attempt_count=attempt_count+1,available_at=:lease
                        WHERE game_id=:game_id AND request_id=:request_id"""),
                        {"lease": now + 300, "game_id": game_id, "request_id": request_id})
                return MemoryBatch(player_id, items)
        return None

    def complete(self, batch: MemoryBatch) -> None:
        with self.engine.begin() as db:
            for game_id, request_id, _ in batch.items:
                db.execute(text("""DELETE FROM player_memory_inputs
                    WHERE game_id=:game_id AND request_id=:request_id"""),
                    {"game_id": game_id, "request_id": request_id})
            db.execute(text("""UPDATE player_memory_settings SET last_generated_at=:now
                WHERE player_id=:player_id AND enabled=TRUE"""),
                {"now": int(time.time()), "player_id": batch.player_id})

    def fail(self, batch: MemoryBatch) -> None:
        now = int(time.time())
        with self.engine.begin() as db:
            for game_id, request_id, _ in batch.items:
                db.execute(text("""UPDATE player_memory_inputs
                    SET status='pending',available_at=:retry_at
                    WHERE game_id=:game_id AND request_id=:request_id"""),
                    {"retry_at": now + 120, "game_id": game_id, "request_id": request_id})
                db.execute(text("""DELETE FROM player_memory_inputs
                    WHERE game_id=:game_id AND request_id=:request_id AND attempt_count>=3"""),
                    {"game_id": game_id, "request_id": request_id})

    def clear(self, player_id: str) -> None:
        with self.engine.begin() as db:
            db.execute(text("DELETE FROM player_memory_inputs WHERE player_id=:player_id"),
                       {"player_id": player_id})
            db.execute(text("""UPDATE player_memory_settings SET last_generated_at=0
                WHERE player_id=:player_id"""), {"player_id": player_id})

    def pending_count(self, player_id: str) -> int:
        with self.engine.connect() as db:
            return int(db.execute(text("""SELECT COUNT(*) FROM player_memory_inputs
                WHERE player_id=:player_id AND status IN ('pending','processing')"""),
                {"player_id": player_id}).scalar_one())
