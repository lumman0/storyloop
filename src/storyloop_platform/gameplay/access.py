"""Visible scenario resolution and shared supported-save invariant."""

from __future__ import annotations

from storyloop_harness import GameStore

from storyloop_platform.portal.catalog import GameCatalog, GameListing
from storyloop_platform.portal.models import SaveRecord
from storyloop_platform.portal.moderation import ScenarioModerationService
from storyloop_platform.portal.turn_errors import TurnInputError
from storyloop_platform.portal.user_scenarios import UserScenarioService


class GameAccess:
    def __init__(self, *, catalog: GameCatalog, user_scenarios: UserScenarioService,
                 moderation: ScenarioModerationService) -> None:
        self.catalog = catalog
        self.user_scenarios = user_scenarios
        self.moderation = moderation

    def listings(self, player_id: str) -> tuple[GameListing, ...]:
        listings = {item.game_id: item for item in self.catalog.list_games()}
        listings.update({item.game_id: item for item in self.user_scenarios.list_playable(player_id)})
        listings.update({item.game_id: item for item in self.moderation.public_listings()})
        return tuple(listings.values())

    def listing_for(self, player_id: str, catalog_id: str,
                     package_hash: str | None = None) -> GameListing:
        try:
            return self.catalog.get(catalog_id)
        except KeyError:
            if catalog_id.startswith("usr_"):
                try:
                    return self.moderation.public_listing(catalog_id, package_hash)
                except KeyError:
                    return self.user_scenarios.get_listing(player_id, catalog_id, package_hash)
            raise

    def verified_listing(self, record: SaveRecord) -> GameListing:
        preview_submission = self.moderation.preview_for(record.game_id, record.player_id)
        item = (self.moderation.preview_listing(record.player_id, preview_submission,
                                                record.package_hash)
                if preview_submission else
                self.listing_for(record.player_id, record.catalog_id, record.package_hash))
        if ((item.package_id, item.package_version, item.fingerprint)
                != (record.package_id, record.package_version, record.package_hash)):
            raise ValueError("scenario package changed; this save needs an explicit migration")
        return item

def require_supported_save(store: GameStore, game_id: str) -> None:
    if any(work.kind == "npc_reply" for work in store.pending_work(game_id)):
        raise TurnInputError("Unsupported legacy save (npc_reply); delete this save and start a new game.")
