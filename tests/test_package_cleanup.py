"""Deleted metadata must retain a durable, reference-checked cleanup intent."""

from sqlalchemy import text
import json

from test_scenario_lifecycle_concurrency import portal, archive


def test_failed_package_delete_can_be_retried_from_persistent_queue(portal, monkeypatch):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Draft", "", archive())
    store = portal.user_scenarios.package_store
    reference = f"{draft['id']}/{draft['version_id']}"
    remove = store.remove

    def locked_file(_reference):
        raise PermissionError("package file is temporarily locked")

    monkeypatch.setattr(store, "remove", locked_file)
    assert portal.delete_scenario_draft(token, draft["id"])["status"] == "deleted"
    with portal.engine.connect() as db:
        queued = db.execute(text("SELECT * FROM package_cleanup_queue")).mappings().all()
    assert len(queued) == 1
    assert queued[0]["package_ref"] == reference
    assert queued[0]["attempts"] == 1
    assert store.materialize(reference).is_dir()
    monkeypatch.setattr(store, "remove", remove)
    # Reconstruct the cleanup service: its retry inputs must live in SQL.
    from storyloop_platform.portal.package_cleanup import PackageCleanup
    cleanup = PackageCleanup(portal.engine, store)
    assert cleanup.retry()[0]["status"] == "removed"
    assert cleanup.pending() == []
    assert not store.materialize(reference).exists()


def test_cleanup_queue_never_deletes_a_package_still_referenced_by_a_version(portal):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Draft", "", archive())
    reference = f"{draft['id']}/{draft['version_id']}"
    from storyloop_platform.portal.package_cleanup import PackageCleanup
    cleanup = PackageCleanup(portal.engine, portal.user_scenarios.package_store)
    with portal.engine.begin() as db:
        cleanup.enqueue(db, reference)
    assert cleanup.retry()[0]["status"] == "referenced"
    assert portal.user_scenarios.package_store.materialize(reference).is_dir()
    assert len(cleanup.pending()) == 1


def test_inspection_reports_missing_and_untracked_packages_without_deleting(portal, capsys):
    token = portal.register("author", "password-123")["token"]
    draft = portal.upload_scenario(token, "Draft", "", archive())
    reference = f"{draft['id']}/{draft['version_id']}"
    store = portal.user_scenarios.package_store
    (store.materialize(reference) / "manifest.json").unlink()
    orphan = f"usr_{'a' * 32}/{'b' * 32}"
    store.materialize(orphan).mkdir(parents=True)
    from storyloop_platform.portal.package_cleanup import inspect_local_packages
    report = inspect_local_packages(portal.engine, store.directory)
    assert reference in report["missing_manifests"]
    assert orphan in report["untracked_packages"]
    assert store.materialize(orphan).is_dir()
    from storyloop_platform.cli.package_cleanup import main
    assert main(["--db", portal.db_path, "--uploads", str(store.directory)]) == 0
    assert orphan in json.loads(capsys.readouterr().out)["untracked_packages"]
    assert store.materialize(orphan).is_dir()
