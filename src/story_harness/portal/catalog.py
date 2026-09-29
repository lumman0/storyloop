"""Explicit catalog of playable scenario packages."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

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


class GameCatalog:
    def __init__(self, listings: tuple[GameListing, ...]) -> None:
        if len({item.game_id for item in listings}) != len(listings):
            raise ValueError("duplicate catalog game ID")
        self._listings = {item.game_id: item for item in listings}

    @classmethod
    def load(cls, path: str | Path) -> GameCatalog:
        source = Path(path).resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        games = raw.get("games") if isinstance(raw, dict) else None
        if not isinstance(games, list) or not games:
            raise ValueError("catalog requires a nonempty games list")
        listings: list[GameListing] = []
        for item in games:
            if not isinstance(item, dict) or any(
                not isinstance(item.get(key), str) or not item[key].strip()
                for key in ("id", "title", "mode", "package")
            ):
                raise ValueError("catalog game requires id, title, mode, and package")
            if item["mode"] not in {"campaign", "freeform"}:
                raise ValueError("catalog game mode must be campaign or freeform")
            package_path = (source.parent / item["package"]).resolve()
            package = ScenarioPackage.load(package_path)
            if item["mode"] == "campaign":
                program = CampaignProgram.load(package_path / "campaign.json")
                if program.program_id != package.package_id or program.ticks_per_day != package.ticks_per_day:
                    raise ValueError("catalog campaign does not match scenario")
            listings.append(GameListing(item["id"], item["title"], item["mode"], package_path,
                                        package.package_id, package.version,
                                        _package_fingerprint(package_path, item["mode"])))
        return cls(tuple(listings))

    def list_games(self) -> tuple[GameListing, ...]:
        return tuple(self._listings.values())

    def get(self, game_id: str) -> GameListing:
        try:
            item = self._listings[game_id]
        except KeyError as error:
            raise KeyError("unknown catalog game") from error
        try:
            current_fingerprint = _package_fingerprint(item.package_path, item.mode)
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("scenario package is unavailable") from error
        if current_fingerprint != item.fingerprint:
            raise ValueError("scenario package changed; reload the catalog before creating a new game")
        return item
