"""Catalog metadata and published package bytes can use separate providers."""

import json
import shutil
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from storyloop_platform.portal.catalog import GameCatalog
from storyloop_platform.config import load_settings
from storyloop_platform.portal.service import PlayerPortal


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "freeform"


class InMemoryCatalogSource:
    def games(self):
        return [{"id": "sample", "title": "Sample", "mode": "freeform",
                 "package": "published/sample/v1"}]


class MovingPackageStore:
    def __init__(self, path):
        self.path = path
        self.references = []

    def materialize(self, reference):
        self.references.append(reference)
        return self.path


class ScenarioStorageTests(unittest.TestCase):
    def test_independent_providers_keep_catalog_identity_and_follow_cache_moves(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "cache-1"
            second = Path(temp) / "cache-2"
            shutil.copytree(EXAMPLE, first)
            shutil.copytree(EXAMPLE, second)
            store = MovingPackageStore(first)
            catalog = GameCatalog.from_sources(InMemoryCatalogSource(), store)

            listing = catalog.get("sample")
            self.assertEqual(listing.package_path, first.resolve())
            self.assertEqual(listing.package_version,
                             json.loads((first / "manifest.json").read_text(encoding="utf-8"))["version"])
            store.path = second
            self.assertEqual(catalog.get("sample").package_path, second.resolve())
            self.assertEqual(store.references, ["published/sample/v1"] * 3)

    def test_changed_materialized_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "cache"
            shutil.copytree(EXAMPLE, package)
            store = MovingPackageStore(package)
            catalog = GameCatalog.from_sources(InMemoryCatalogSource(), store)
            manifest = package / "manifest.json"
            manifest.write_bytes(manifest.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "scenario package changed"):
                catalog.get("sample")

    def test_portal_lists_games_from_injected_catalog(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_MODEL_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": ""},
        ):
            root = Path(__file__).resolve().parents[1]
            catalog = GameCatalog.from_sources(InMemoryCatalogSource(), MovingPackageStore(EXAMPLE))
            portal = PlayerPortal(None, load_settings(root / "config" / "local.json"),
                                  str(Path(temp) / "game.sqlite3"),
                                  catalog=catalog)
            try:
                token = portal.register("storage-test", "storage-pass-123")["token"]
                self.assertEqual([game["id"] for game in portal.games(token)], ["sample"])
            finally:
                portal.close()
