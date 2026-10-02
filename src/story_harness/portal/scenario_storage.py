"""Storage boundaries for published scenario metadata and package files.

The runtime consumes a local directory. A remote package store may download an
immutable object into a cache, then return that directory to the catalog.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Protocol


class ScenarioCatalogSource(Protocol):
    def games(self) -> list[dict]:
        """Return published listing metadata with opaque package references."""
        ...


class ScenarioPackageStore(Protocol):
    def materialize(self, reference: str) -> Path:
        """Return a local directory containing the referenced package."""
        ...


class PublishedPackageStore(ScenarioPackageStore, Protocol):
    def publish(self, reference: str, source: Path) -> None:
        """Persist a validated immutable package under a server-generated reference."""
        ...

    def remove(self, reference: str) -> None:
        """Discard a package when metadata persistence fails."""
        ...


class LocalScenarioCatalogSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def games(self) -> list[dict]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        games = raw.get("games") if isinstance(raw, dict) else None
        if not isinstance(games, list) or not games:
            raise ValueError("catalog requires a nonempty games list")
        return games


class LocalScenarioPackageStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()

    def materialize(self, reference: str) -> Path:
        return (self.directory / reference).resolve()


class LocalPublishedPackageStore:
    """Writable local store restricted to generated two-segment references."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).resolve()

    def materialize(self, reference: str) -> Path:
        if not re.fullmatch(r"usr_[0-9a-f]{32}/[0-9a-f]{32}", reference):
            raise ValueError("invalid published package reference")
        return self.directory / reference

    def publish(self, reference: str, source: Path) -> None:
        target = self.materialize(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError("published package version already exists")
        source.rename(target)

    def remove(self, reference: str) -> None:
        target = self.materialize(reference)
        if target.exists():
            shutil.rmtree(target)
        if target.parent.exists() and not any(target.parent.iterdir()):
            target.parent.rmdir()
