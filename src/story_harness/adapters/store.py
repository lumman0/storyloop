from __future__ import annotations

from typing import Protocol

from story_harness.adapters.sql_database import open_database, sqlite_url, upgrade_database
from story_harness.adapters.sql_store import SQLGameStore
from story_harness.core.contracts import Observation, PendingWork, PlayerInput, Snapshot, WorldEvent


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


class SQLiteGameStore(SQLGameStore):
    """Compatibility entry point backed by the shared SQL repository."""

    def __init__(self, path: str) -> None:
        self.path = path
        url = sqlite_url(path)
        upgrade_database(url)
        super().__init__(open_database(url))
