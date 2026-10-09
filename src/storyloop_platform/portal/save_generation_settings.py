"""Persistent, per-save generation options, independent of the database dialect."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class SaveGenerationSettings:
    temperature: float
    context_window_tokens: int


class SQLSaveGenerationSettings:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, game_id: str, defaults: SaveGenerationSettings) -> SaveGenerationSettings:
        with self.engine.connect() as db:
            row = db.execute(text("""SELECT temperature,context_window_tokens
                FROM save_generation_settings WHERE game_id=:game_id"""),
                {"game_id": game_id}).mappings().first()
        return (SaveGenerationSettings(float(row["temperature"]), int(row["context_window_tokens"]))
                if row else defaults)

    def put(self, game_id: str, settings: SaveGenerationSettings,
            previous: SaveGenerationSettings) -> None:
        with self.engine.begin() as db:
            db.execute(text("""INSERT INTO save_generation_settings
                (game_id,temperature,context_window_tokens)
                VALUES (:game_id,:temperature,:context_window_tokens)
                ON CONFLICT (game_id) DO UPDATE SET
                    temperature=excluded.temperature,
                    context_window_tokens=excluded.context_window_tokens"""),
                {"game_id": game_id, "temperature": settings.temperature,
                 "context_window_tokens": settings.context_window_tokens})
            if settings.context_window_tokens > previous.context_window_tokens:
                # The authoritative events remain available; rebuild each actor's
                # prompt from them when a larger budget is chosen.
                db.execute(text("DELETE FROM agent_contexts WHERE game_id=:game_id"),
                           {"game_id": game_id})
