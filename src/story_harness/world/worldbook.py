"""Versioned exact worldbook with visibility filtering before retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorldbookEntry:
    entry_id: str
    text: str
    visibility: str
    allowed_actors: frozenset[str]
    kind: str = "lore"
    source: str | None = None


class Worldbook:
    def __init__(
        self, package_id: str, version: str, entries: list[WorldbookEntry]
    ) -> None:
        self.package_id = package_id
        self.version = version
        self._entries = {entry.entry_id: entry for entry in entries}
        if len(self._entries) != len(entries):
            raise ValueError("duplicate worldbook entry ID")

    @classmethod
    def load(cls, path: str | Path) -> Worldbook:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data.get("package_id"), str) or not data["package_id"]:
            raise ValueError("worldbook requires package_id")
        if not isinstance(data.get("version"), str) or not data["version"]:
            raise ValueError("worldbook requires version")
        entries: list[WorldbookEntry] = []
        for raw in data.get("entries", []):
            visibility = raw.get("visibility", "public")
            if visibility not in {"public", "actor", "secret"}:
                raise ValueError(f"invalid visibility: {visibility}")
            allowed = raw.get("allowed_actors", [])
            if not isinstance(allowed, list) or not all(
                isinstance(actor, str) for actor in allowed
            ):
                raise ValueError("allowed_actors must be a list of IDs")
            entry_id = raw.get("id")
            text = raw.get("text")
            if not isinstance(entry_id, str) or not entry_id:
                raise ValueError("worldbook entry requires an ID")
            if not isinstance(text, str) or not text:
                raise ValueError(f"worldbook entry {entry_id} requires text")
            kind = raw.get("kind", "lore")
            source = raw.get("source")
            if kind not in {"lore", "rule", "card", "truth"}:
                raise ValueError(f"invalid worldbook entry kind: {kind}")
            if source is not None and (not isinstance(source, str) or not source):
                raise ValueError(f"invalid source for {entry_id}")
            entries.append(
                WorldbookEntry(entry_id, text, visibility, frozenset(allowed), kind, source)
            )
        return cls(data["package_id"], data["version"], entries)

    @staticmethod
    def _can_read(
        entry: WorldbookEntry, viewer: str, grants: set[str] | frozenset[str]
    ) -> bool:
        return (
            viewer == "system"
            or entry.visibility == "public"
            or entry.entry_id in grants
            or (entry.visibility == "actor" and viewer in entry.allowed_actors)
        )

    def get(
        self,
        entry_id: str,
        viewer: str,
        grants: set[str] | frozenset[str] = frozenset(),
    ) -> WorldbookEntry | None:
        entry = self._entries.get(entry_id)
        if entry is None or not self._can_read(entry, viewer, grants):
            return None
        return entry

    def retrieve(
        self,
        query: str,
        viewer: str,
        grants: set[str] | frozenset[str] = frozenset(),
        limit: int = 5,
    ) -> list[WorldbookEntry]:
        if limit < 0:
            raise ValueError("limit cannot be negative")
        if not query:
            return []
        needle = query.casefold()
        return [
            entry
            for entry in self._entries.values()
            if self._can_read(entry, viewer, grants)
            and needle in entry.text.casefold()
        ][:limit]

    def visible_lore(self, viewer: str, limit: int = 4) -> tuple[WorldbookEntry, ...]:
        """Return setting material safe to use in player-facing scene prose."""
        if limit < 0:
            raise ValueError("limit cannot be negative")
        return tuple(entry for entry in self._entries.values()
                     if entry.kind == "lore" and self._can_read(entry, viewer, frozenset()))[:limit]
