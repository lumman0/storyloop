"""Author-owned scenario upload and private publication."""

from __future__ import annotations

import io
import asyncio
import concurrent.futures
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from storyloop_platform.portal.http_api import create_app
from storyloop_platform.portal.service import PlayerPortal
from storyloop_platform.portal.user_scenarios import UserScenarioService
from storyloop_platform.portal import user_scenarios as upload_module


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "freeform"


def archive(files: dict[str, bytes] | None = None) -> bytes:
    contents = files or {file.name: file.read_bytes() for file in EXAMPLE.glob("*.json")}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in contents.items():
            bundle.writestr(name, data)
    return output.getvalue()


class UserScenarioUploadTests(unittest.TestCase):
    def portal(self, directory: Path) -> PlayerPortal:
        return PlayerPortal(ROOT / "config" / "games.example.json",
                            ROOT / "config" / "local.json", str(directory / "portal.sqlite3"),
                            prologue_generator=lambda *_: "固定开场。\n\n现在可以开始故事。")

    def test_missing_prologue_is_generated_once_for_each_saved_version(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            calls: list[str] = []

            def generate(package, program, title, summary):
                calls.append(package.version)
                return f"第{len(calls)}版序章。\n\n从这里开始。"

            portal.user_scenarios.prologue_generator = generate
            try:
                token = portal.register("author", "upload-pass-123")["token"]
                first = portal.upload_scenario(token, "故事", "背景", archive())
                first_package = portal.user_scenarios.package_store.materialize(
                    f"{first['id']}/{first['version_id']}")
                self.assertEqual(json.loads((first_package / "manifest.json").read_text(
                    encoding="utf-8"))["authored_prologue"], "第1版序章。\n\n从这里开始。")
                portal.publish_scenario(token, first["id"])
                view = asyncio.run(portal.create_save(token, first["id"]))
                self.assertEqual(view["opening"], "第1版序章。\n\n从这里开始。")
                asyncio.run(portal.resume_save(token, view["game_id"]))
                self.assertEqual(len(calls), 1)
                portal.upload_scenario_version(token, first["id"], "故事", "背景", archive())
                self.assertEqual(len(calls), 2)
            finally:
                portal.close()

    def test_upload_stays_private_until_author_publishes(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            try:
                author = portal.register("author", "upload-pass-123")["token"]
                other = portal.register("reader", "upload-pass-123")["token"]
                item = portal.upload_scenario(author, "我的世界", "仅供试玩", archive())
                self.assertEqual(item["status"], "draft")
                self.assertNotIn(item["id"], [game["id"] for game in portal.games(author)])
                with self.assertRaises(PermissionError):
                    portal.publish_scenario(other, item["id"])
                published = portal.publish_scenario(author, item["id"])
                self.assertEqual(published["status"], "published")
                self.assertIn(item["id"], [game["id"] for game in portal.games(author)])
                self.assertNotIn(item["id"], [game["id"] for game in portal.games(other)])
                self.assertEqual(portal.my_scenarios(author)[0]["title"], "我的世界")
                self.assertEqual(portal.my_scenarios(other), [])
                with self.assertRaises(PermissionError):
                    asyncio.run(portal.create_save(other, item["id"]))
                view = asyncio.run(portal.create_save(author, item["id"]))
                self.assertEqual(view["catalog_id"], item["id"])
            finally:
                portal.close()
            reopened = self.portal(Path(temp))
            try:
                self.assertIn(item["id"], [game["id"] for game in reopened.games(author)])
                self.assertTrue(reopened.saves(author)[0]["available"])
            finally:
                reopened.close()

    def test_http_upload_requires_authentication_and_accepts_zip(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            with TestClient(create_app(portal), base_url="http://127.0.0.1") as client:
                payload = archive()
                endpoint = "/v1/my-scenarios"
                form = {"data": {"title": "HTTP剧本", "summary": "私有"},
                        "files": {"file": ("scenario.zip", payload, "application/zip")}}
                self.assertEqual(client.post(endpoint, **form).status_code, 401)
                token = client.post("/v1/accounts", json={"username": "uploader",
                    "password": "upload-pass-123"}).json()["token"]
                headers = {"Authorization": f"Bearer {token}"}
                result = client.post(endpoint, headers=headers, **form)
                self.assertEqual(result.status_code, 201, result.text)
                scenario_id = result.json()["id"]
                self.assertEqual(client.get("/v1/my-scenarios", headers=headers).json()["scenarios"][0]["id"],
                                 scenario_id)
                self.assertEqual(client.post(f"/v1/my-scenarios/{scenario_id}/publish",
                                             headers=headers).status_code, 200)
                self.assertEqual(client.delete(f"/v1/my-scenarios/{scenario_id}",
                                               headers=headers).status_code, 400)
                self.assertIn(scenario_id, [game["id"] for game in client.get("/v1/catalog",
                    headers=headers).json()["games"]])
                self.assertEqual(client.post(endpoint, headers=headers, data=form["data"],
                    files={"file": ("notes.txt", b"not a ZIP", "text/plain")}).status_code, 415)
                self.assertEqual(client.post(endpoint, headers=headers, data=form["data"],
                    files={"file": ("large.zip", b"x" * (4 * 1024 * 1024 + 1),
                                    "application/zip")}).status_code, 413)

    def test_unsafe_archive_is_rejected_without_creating_draft(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            try:
                token = portal.register("author", "upload-pass-123")["token"]
                for malicious in ({"../outside.json": b"{}"}, {"C:outside.json": b"{}"},
                                  {"CON.json": b"{}"}, {"script.py": b"print('bad')"},
                                  {"manifest.json": b"{}"}):
                    with self.subTest(malicious=malicious):
                        with self.assertRaises(ValueError):
                            portal.upload_scenario(token, "Bad", "", archive(malicious))
                valid = {file.name: file.read_bytes() for file in EXAMPLE.glob("*.json")}
                for unsafe_name in ("C:outside.json", "CON.json", "name\n.json"):
                    with self.subTest(unsafe_name=unsafe_name):
                        with self.assertRaisesRegex(ValueError, "unsafe"):
                            portal.upload_scenario(token, "Bad", "", archive({
                                **valid, unsafe_name: b"{}",
                            }))
                self.assertEqual(portal.my_scenarios(token), [])
            finally:
                portal.close()

    def test_zip_symlink_and_large_unpacked_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            try:
                token = portal.register("author", "upload-pass-123")["token"]
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as bundle:
                    link = zipfile.ZipInfo("manifest.json")
                    link.create_system = 3
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    bundle.writestr(link, "target")
                with self.assertRaises(ValueError):
                    portal.upload_scenario(token, "Bad", "", output.getvalue())
                with self.assertRaisesRegex(ValueError, "limit"):
                    portal.upload_scenario(token, "Bad", "", archive({
                        "manifest.json": b"x" * (2 * 1024 * 1024 + 1),
                    }))
            finally:
                portal.close()

    def test_package_writer_can_be_replaced_without_changing_upload_flow(self):
        class RecordingStore:
            def __init__(self, root):
                self.root = root
                self.published = []

            def materialize(self, reference):
                return self.root / reference

            def publish(self, reference, source):
                self.published.append(reference)
                target = self.materialize(reference)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source, target)

            def remove(self, reference):
                shutil.rmtree(self.materialize(reference), ignore_errors=True)

        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            try:
                store = RecordingStore(Path(temp) / "packages")
                portal.user_scenarios = UserScenarioService(portal.engine, Path(temp) / "uploads",
                                                            package_store=store,
                                                            prologue_generator=lambda *_: "固定开场。")
                token = portal.register("author", "upload-pass-123")["token"]
                item = portal.upload_scenario(token, "Custom", "", archive())
                self.assertEqual(len(store.published), 1)
                portal.publish_scenario(token, item["id"])
                self.assertTrue(store.materialize(store.published[0]).is_dir())
                self.assertEqual(list((Path(temp) / "uploads" / ".staging").iterdir()), [])
            finally:
                portal.close()

    def test_official_catalog_id_with_usr_prefix_still_plays(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            catalog = Path(temp) / "official.json"
            catalog.write_text(json.dumps({"games": [{"id": "usr_event", "title": "Official",
                "mode": "freeform", "package": str(EXAMPLE)}]}), encoding="utf-8")
            portal = PlayerPortal(catalog, ROOT / "config" / "local.json",
                                  str(Path(temp) / "portal.sqlite3"))
            try:
                token = portal.register("author", "upload-pass-123")["token"]
                view = asyncio.run(portal.create_save(token, "usr_event"))
                self.assertEqual(view["catalog_id"], "usr_event")
            finally:
                portal.close()

    def test_concurrent_uploads_obey_author_quota(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ):
            portal = self.portal(Path(temp))
            try:
                token = portal.register("author", "upload-pass-123")["token"]
                barrier = threading.Barrier(2)
                real_extract = upload_module._extract_package

                def synchronized_extract(data, directory):
                    real_extract(data, directory)
                    barrier.wait(timeout=5)

                with patch.object(upload_module, "MAX_SCENARIOS_PER_AUTHOR", 1), \
                     patch.object(upload_module, "_extract_package", side_effect=synchronized_extract):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        futures = [pool.submit(portal.upload_scenario, token, "Concurrent", "", archive())
                                   for _ in range(2)]
                        outcomes = []
                        for future in futures:
                            try:
                                outcomes.append(future.result(timeout=10)["status"])
                            except ValueError:
                                outcomes.append("quota")
                self.assertEqual(sorted(outcomes), ["draft", "quota"])
                self.assertEqual(len(portal.my_scenarios(token)), 1)
            finally:
                portal.close()

    def test_author_can_delete_only_unpublished_draft_and_reuse_quota(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"STORY_BAILIAN_API_KEY": "offline-test", "LANGFUSE_PUBLIC_KEY": "",
                         "LANGFUSE_SECRET_KEY": "", "STORY_UPLOAD_DIR": str(Path(temp) / "uploads")},
        ), patch.object(upload_module, "MAX_SCENARIOS_PER_AUTHOR", 1):
            portal = self.portal(Path(temp))
            try:
                author = portal.register("author", "upload-pass-123")["token"]
                other = portal.register("other", "upload-pass-123")["token"]
                draft = portal.upload_scenario(author, "First", "", archive())
                with self.assertRaises(PermissionError):
                    portal.delete_scenario_draft(other, draft["id"])
                with self.assertRaisesRegex(ValueError, "limit"):
                    portal.upload_scenario(author, "Second", "", archive())
                portal.delete_scenario_draft(author, draft["id"])
                self.assertEqual(portal.my_scenarios(author), [])
                self.assertFalse((Path(temp) / "uploads" / draft["id"]).exists())
                self.assertEqual(portal.upload_scenario(author, "Second", "", archive())["status"],
                                 "draft")
            finally:
                portal.close()
