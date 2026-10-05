"""Scenario lifecycle commands must serialize across request threads."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
import asyncio
import io
import threading
from pathlib import Path
import zipfile

import pytest
from sqlalchemy import event, text

from story_harness.portal.service import PlayerPortal


ROOT = Path(__file__).resolve().parents[1]


def archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in (ROOT / "examples/freeform").glob("*.json"):
            bundle.write(path, path.name)
    return buffer.getvalue()


@pytest.fixture
def portal(tmp_path, monkeypatch):
    monkeypatch.setenv("STORY_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("STORY_BAILIAN_API_KEY", "offline-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    instance = PlayerPortal(ROOT / "config/games.example.json", ROOT / "config/local.json",
                            str(tmp_path / "test.sqlite3"),
                            prologue_generator=lambda *_: "A quiet opening.")
    try:
        yield instance
    finally:
        instance.close()


@pytest.mark.parametrize("command", ["publish_scenario", "submit_scenario"])
def test_delete_cannot_remove_a_concurrently_published_or_submitted_scenario(portal, command):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Story", "", archive())
    deleting = threading.Event()
    release = threading.Event()

    def pause_delete(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM user_scenario_versions"):
            deleting.set()
            assert release.wait(10), "delete barrier timed out"

    event.listen(portal.engine, "before_cursor_execute", pause_delete)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            deletion = pool.submit(portal.delete_scenario_draft, token, draft["id"])
            try:
                assert deleting.wait(10)
                publication = pool.submit(getattr(portal, command), token, draft["id"])
                try:
                    publication.result(timeout=0.3)
                except TimeoutError:
                    pass  # The database lock is allowed to serialize the commands.
            finally:
                release.set()
            deletion.result(timeout=10)
            try:
                published = publication.result(timeout=10)
            except (KeyError, ValueError):
                published = None
    finally:
        event.remove(portal.engine, "before_cursor_execute", pause_delete)
    assert published is None, "publication reported success even though its package was deleted"
    with portal.engine.connect() as db:
        assert db.execute(text("SELECT COUNT(*) FROM scenario_submissions")).scalar_one() == 0


def test_version_upload_revalidates_after_slow_generation(portal):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Story", "", archive())
    generating = threading.Event()
    release = threading.Event()

    def generate(*args):
        generating.set()
        assert release.wait(10), "generation barrier timed out"
        return "A revised opening."

    portal.user_scenarios.prologue_generator = generate
    with ThreadPoolExecutor(max_workers=1) as pool:
        upload = pool.submit(portal.upload_scenario_version, token, draft["id"],
                             "Revision", "", archive())
        try:
            assert generating.wait(10)
            portal.delete_scenario_draft(token, draft["id"])
        finally:
            release.set()
        with pytest.raises(KeyError, match="scenario not found"):
            upload.result(timeout=10)
    with portal.engine.connect() as db:
        assert db.execute(text("SELECT COUNT(*) FROM user_scenario_versions")).scalar_one() == 0
    assert not portal.user_scenarios.package_store.materialize(
        f"{draft['id']}/{draft['version_id']}").parent.exists()


def test_post_commit_response_failure_does_not_remove_a_saved_version(portal, monkeypatch):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Story", "", archive())

    def unavailable_list(*args):
        raise RuntimeError("database connection lost after commit")

    monkeypatch.setattr(portal.user_scenarios, "list_mine", unavailable_list)
    with pytest.raises(RuntimeError, match="after commit"):
        portal.upload_scenario_version(token, draft["id"], "Revision", "", archive())
    with portal.engine.connect() as db:
        references = db.execute(text("SELECT package_ref FROM user_scenario_versions")).scalars().all()
    assert len(references) == 2
    assert all(portal.user_scenarios.package_store.materialize(ref).is_dir() for ref in references)


@pytest.mark.parametrize("command, barrier_sql", [
    ("publish_scenario", "UPDATE user_scenario_versions SET published_at"),
    ("submit_scenario", "INSERT INTO scenario_submissions"),
])
def test_publication_winning_the_race_protects_its_package(portal, command, barrier_sql):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Story", "", archive())
    publishing = threading.Event()
    release = threading.Event()

    def pause_publication(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith(barrier_sql):
            publishing.set()
            assert release.wait(10), "publication barrier timed out"

    event.listen(portal.engine, "before_cursor_execute", pause_publication)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            publication = pool.submit(getattr(portal, command), token, draft["id"])
            try:
                assert publishing.wait(10)
                deletion = pool.submit(portal.delete_scenario_draft, token, draft["id"])
            finally:
                release.set()
            publication.result(timeout=10)
            with pytest.raises(ValueError, match="cannot be deleted"):
                deletion.result(timeout=10)
    finally:
        event.remove(portal.engine, "before_cursor_execute", pause_publication)
    package = portal.user_scenarios.package_store.materialize(f"{draft['id']}/{draft['version_id']}")
    assert (package / "manifest.json").is_file()
    if command == "publish_scenario":
        saved = asyncio.run(portal.create_save(token, draft["id"]))
        assert asyncio.run(portal.resume_save(token, saved["game_id"]))["game_id"] == saved["game_id"]
