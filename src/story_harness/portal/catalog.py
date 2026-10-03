"""Explicit catalog of playable scenario packages."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from story_harness.portal.scenario_storage import (
    LocalScenarioCatalogSource, LocalScenarioPackageStore,
    ScenarioCatalogSource, ScenarioPackageStore,
)
from story_harness.runtime.campaign import CampaignProgram
from story_harness.world.scenario import ScenarioPackage


def _package_fingerprint(package_path: Path, mode: str) -> str:
    manifest = json.loads((package_path / "manifest.json").read_text(encoding="utf-8"))
    files = [package_path / "manifest.json", package_path / manifest["worldbook"]]
    if mode == "campaign":
        files.append(package_path / "campaign.json")
    digest = hashlib.sha256()
    for file in files:
        content = file.read_bytes()
        digest.update(str(file.relative_to(package_path)).encode("utf-8"))
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


@dataclass(frozen=True)
class GameListing:
    game_id: str
    title: str
    mode: str
    package_path: Path
    package_id: str
    package_version: str
    fingerprint: str
    summary: str = ""
    genre: str = ""
    theme: str = "harbor"
    turns_per_story_tick: int = 1
    retired: bool = False
    play_modes: tuple[str, ...] = ()

    @property
    def supported_play_modes(self) -> tuple[str, ...]:
        if self.play_modes:
            return self.play_modes
        return (self.mode,)


class GameCatalog:
    def __init__(self, listings: tuple[GameListing, ...],
                 package_store: ScenarioPackageStore | None = None,
                 package_refs: dict[str, str] | None = None) -> None:
        if len({item.game_id for item in listings}) != len(listings):
            raise ValueError("duplicate catalog game ID")
        self._listings = {item.game_id: item for item in listings}
        self._package_store = package_store
        self._package_refs = package_refs or {}

    @classmethod
    def load(cls, path: str | Path) -> GameCatalog:
        source = Path(path).resolve()
        return cls.from_sources(LocalScenarioCatalogSource(source),
                                LocalScenarioPackageStore(source.parent))

    @classmethod
    def from_sources(cls, catalog_source: ScenarioCatalogSource,
                     package_store: ScenarioPackageStore) -> GameCatalog:
        games = catalog_source.games()
        if not isinstance(games, list) or not games:
            raise ValueError("catalog requires a nonempty games list")
        listings: list[GameListing] = []
        package_refs: dict[str, str] = {}
        for item in games:
            if not isinstance(item, dict) or any(
                not isinstance(item.get(key), str) or not item[key].strip()
                for key in ("id", "title", "mode", "package")
            ):
                raise ValueError("catalog game requires id, title, mode, and package")
            if item["mode"] not in {"campaign", "freeform"}:
                raise ValueError("catalog game mode must be campaign or freeform")
            play_modes = item.get("play_modes")
            if play_modes is not None and (
                not isinstance(play_modes, list) or not play_modes
                or any(not isinstance(mode, str) or mode not in {"campaign", "freeform"}
                       for mode in play_modes)
                or len(set(play_modes)) != len(play_modes)
                or item["mode"] not in play_modes
                or (item["mode"] == "freeform" and "campaign" in play_modes)
            ):
                raise ValueError("catalog play_modes must include its authored mode")
            turns_per_story_tick = item.get("turns_per_story_tick", 1)
            if type(turns_per_story_tick) is not int or turns_per_story_tick < 1:
                raise ValueError("turns_per_story_tick must be positive")
            retired = item.get("retired", False)
            if type(retired) is not bool:
                raise ValueError("catalog game retired must be a boolean")
            for field in ("summary", "genre", "theme"):
                if field in item and not isinstance(item[field], str):
                    raise ValueError(f"catalog game {field} must be a string")
            package_path = Path(package_store.materialize(item["package"])).resolve()
            package = ScenarioPackage.load(package_path)
            if item["mode"] == "campaign":
                program = CampaignProgram.load(package_path / "campaign.json")
                if program.program_id != package.package_id or program.ticks_per_day != package.ticks_per_day:
                    raise ValueError("catalog campaign does not match scenario")
            listings.append(GameListing(item["id"], item["title"], item["mode"], package_path,
                                        package.package_id, package.version,
                                        _package_fingerprint(package_path, item["mode"]),
                                        item.get("summary", ""), item.get("genre", ""),
                                        item.get("theme", "harbor"), turns_per_story_tick, retired,
                                        tuple(play_modes) if play_modes is not None else ()))
            package_refs[item["id"]] = item["package"]
        return cls(tuple(listings), package_store, package_refs)

    def list_games(self) -> tuple[GameListing, ...]:
        return tuple(item for item in self._listings.values() if not item.retired)

    def get(self, game_id: str) -> GameListing:
        try:
            item = self._listings[game_id]
        except KeyError as error:
            raise KeyError("unknown catalog game") from error
        try:
            package_path = (Path(self._package_store.materialize(self._package_refs[game_id])).resolve()
                            if self._package_store else item.package_path)
            current_fingerprint = _package_fingerprint(package_path, item.mode)
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("scenario package is unavailable") from error
        if current_fingerprint != item.fingerprint:
            raise ValueError("scenario package changed; reload the catalog before creating a new game")
        return replace(item, package_path=package_path)
