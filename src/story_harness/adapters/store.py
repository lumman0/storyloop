from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from typing import Protocol

from story_harness.core.contracts import Observation, PendingWork, PlayerInput, Snapshot, WorldEvent
from story_harness.core.state import apply_event


class GameStore(Protocol):
    """Storage behavior required by the runner and agent context adapter."""

    def create_game(
        self, snapshot: Snapshot, initial_work: tuple[PendingWork, ...] = ()
    ) -> None: ...

    def load(self, game_id: str) -> Snapshot: ...

    def event_exists(self, game_id: str, event_id: str) -> bool: ...

    def event_details(self, game_id: str, event_id: str) -> dict[str, object] | None: ...

    def completed_turn_count(self, game_id: str) -> int: ...

    def commit(
        self,
        game_id: str,
        expected_version: int,
        event: WorldEvent | None,
        observations: tuple[Observation, ...],
        new_work: tuple[PendingWork, ...],
        consumed_work_id: str | None = None,
    ) -> Snapshot: ...

    def observations_for(self, game_id: str, recipient_id: str) -> list[Observation]: ...

    def dialogue_history_for_actor(self, game_id: str, actor_id: str) -> list[tuple[str, str]]: ...

    def player_inputs_for(self, game_id: str) -> list[PlayerInput]: ...

    def ready_work(self, game_id: str, tick: int) -> list[PendingWork]: ...

    def pending_work(self, game_id: str) -> list[PendingWork]: ...


class SQLiteGameStore:
    """Atomic storage for a game's state, events, observations and work."""

    def __init__(self, path: str) -> None:
        self.path = path
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    tick INTEGER NOT NULL,
                    data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    game_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    actor_id TEXT,
                    cause_id TEXT,
                    tick INTEGER NOT NULL,
                    effects TEXT NOT NULL,
                    details TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    PRIMARY KEY (game_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    game_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    PRIMARY KEY (game_id, observation_id)
                );
                CREATE TABLE IF NOT EXISTS pending_work (
                    game_id TEXT NOT NULL,
                    work_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    due_tick INTEGER NOT NULL,
                    priority INTEGER NOT NULL,
                    cause_id TEXT,
                    payload TEXT NOT NULL,
                    mandatory INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'consumed')),
                    PRIMARY KEY (game_id, work_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> Snapshot:
        return Snapshot(row["game_id"], row["version"], row["tick"], json.loads(row["data"]))

    @staticmethod
    def _work(row: sqlite3.Row) -> PendingWork:
        return PendingWork(
            row["work_id"],
            row["kind"],
            row["due_tick"],
            row["priority"],
            row["cause_id"],
            json.loads(row["payload"]),
            bool(row["mandatory"]),
        )

    def create_game(
        self, snapshot: Snapshot, initial_work: tuple[PendingWork, ...] = ()
    ) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO games VALUES (?, ?, ?, ?)",
                (
                    snapshot.game_id,
                    snapshot.version,
                    snapshot.tick,
                    json.dumps(snapshot.data, ensure_ascii=False),
                ),
            )
            self._insert_work(connection, snapshot.game_id, initial_work)
            connection.commit()
        except (sqlite3.IntegrityError, ValueError) as error:
            connection.rollback()
            raise ValueError(str(error)) from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load(self, game_id: str) -> Snapshot:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
        if row is None:
            raise KeyError(game_id)
        return self._snapshot(row)

    def event_exists(self, game_id: str, event_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM events WHERE game_id = ? AND event_id = ?",
                (game_id, event_id),
            ).fetchone()
        return row is not None

    def event_details(self, game_id: str, event_id: str) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT details FROM events WHERE game_id = ? AND event_id = ?",
                (game_id, event_id),
            ).fetchone()
        return json.loads(row["details"]) if row is not None else None

    def completed_turn_count(self, game_id: str) -> int:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM events WHERE game_id = ? AND kind = 'campaign_turn_completed'",
                (game_id,),
            ).fetchone()
        return int(row["total"])

    def commit(
        self,
        game_id: str,
        expected_version: int,
        event: WorldEvent | None,
        observations: tuple[Observation, ...],
        new_work: tuple[PendingWork, ...],
        consumed_work_id: str | None = None,
    ) -> Snapshot:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
            if row is None:
                raise KeyError(game_id)
            before = self._snapshot(row)
            if before.version != expected_version:
                raise ValueError("game state version changed")

            if consumed_work_id is not None:
                consumed = connection.execute(
                    """UPDATE pending_work SET status = 'consumed'
                       WHERE game_id = ? AND work_id = ? AND status = 'pending'""",
                    (game_id, consumed_work_id),
                )
                if consumed.rowcount != 1:
                    raise ValueError("pending work was already consumed or does not exist")

            after = apply_event(before, event) if event is not None else before
            if event is not None:
                connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        game_id,
                        event.event_id,
                        event.kind,
                        event.actor_id,
                        event.cause_id,
                        event.tick,
                        json.dumps([asdict(effect) for effect in event.effects], ensure_ascii=False),
                        json.dumps(event.details, ensure_ascii=False),
                        after.version,
                    ),
                )
                connection.execute(
                    "UPDATE games SET version = ?, tick = ?, data = ? WHERE game_id = ?",
                    (
                        after.version,
                        after.tick,
                        json.dumps(after.data, ensure_ascii=False),
                        game_id,
                    ),
                )

            for observation in observations:
                source = connection.execute(
                    "SELECT 1 FROM events WHERE game_id = ? AND event_id = ?",
                    (game_id, observation.event_id),
                ).fetchone()
                if source is None:
                    raise ValueError("observation refers to an unknown event")
                connection.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        game_id,
                        observation.observation_id,
                        observation.event_id,
                        observation.recipient_id,
                        observation.channel,
                        observation.content,
                        observation.tick,
                    ),
                )

            self._insert_work(connection, game_id, new_work)
            connection.commit()
            return after
        except (sqlite3.IntegrityError, ValueError) as error:
            connection.rollback()
            raise ValueError(str(error)) from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _insert_work(
        connection: sqlite3.Connection, game_id: str, work: tuple[PendingWork, ...]
    ) -> None:
        for item in work:
            connection.execute(
                "INSERT INTO pending_work VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
                (
                    game_id,
                    item.work_id,
                    item.kind,
                    item.due_tick,
                    item.priority,
                    item.cause_id,
                    json.dumps(item.payload, ensure_ascii=False),
                    int(item.mandatory),
                ),
            )

    def observations_for(self, game_id: str, recipient_id: str) -> list[Observation]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT o.observation_id, o.event_id, o.recipient_id, o.channel, o.content, o.tick
                   FROM observations AS o
                   JOIN events AS e ON e.game_id = o.game_id AND e.event_id = o.event_id
                   WHERE o.game_id = ? AND o.recipient_id = ?
                   ORDER BY e.state_version, o.rowid""",
                (game_id, recipient_id),
            ).fetchall()
        return [Observation(**dict(row)) for row in rows]

    def dialogue_history_for_actor(self, game_id: str, actor_id: str) -> list[tuple[str, str]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT details FROM events
                   WHERE game_id = ? AND actor_id = ? AND kind = 'npc_spoke'
                   ORDER BY state_version""",
                (game_id, actor_id),
            ).fetchall()
        result: list[tuple[str, str]] = []
        for row in rows:
            details = json.loads(row["details"])
            result.append((details["player_message"], details["speech"]))
        return result

    def player_inputs_for(self, game_id: str) -> list[PlayerInput]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT event_id, kind, tick, details FROM events
                   WHERE game_id = ? AND kind IN ('player_input', 'player_query', 'player_action', 'action_rejected')
                     AND actor_id = 'player'
                   ORDER BY state_version""",
                (game_id,),
            ).fetchall()
        result: list[PlayerInput] = []
        for row in rows:
            details = json.loads(row["details"])
            default_channel = {
                "player_query": "query",
                "player_action": "action",
                "action_rejected": "action",
            }.get(row["kind"], "speech")
            result.append(
                PlayerInput(
                    row["event_id"], row["tick"], details["text"],
                    details.get("channel", default_channel),
                    tuple(details.get("target_ids", [])),
                )
            )
        return result

    def ready_work(self, game_id: str, tick: int) -> list[PendingWork]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM pending_work
                   WHERE game_id = ? AND due_tick <= ? AND status = 'pending'
                   ORDER BY due_tick, mandatory DESC, priority DESC, work_id""",
                (game_id, tick),
            ).fetchall()
        return [self._work(row) for row in rows]

    def pending_work(self, game_id: str) -> list[PendingWork]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM pending_work WHERE game_id = ? AND status = 'pending'
                   ORDER BY due_tick, mandatory DESC, priority DESC, work_id""",
                (game_id,),
            ).fetchall()
        return [self._work(row) for row in rows]
