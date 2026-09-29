"""Records shared by portal repository implementations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SaveRecord:
    game_id: str
    player_id: str
    catalog_id: str
    package_id: str
    package_version: str
    package_hash: str
    created_at: int
