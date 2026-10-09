"""Retry explicitly queued deletions; inventory findings never authorize removal."""

import logging
from pathlib import Path
import re
import time

from sqlalchemy import Connection, Engine, text

from storyloop_platform.portal.scenario_storage import PublishedPackageStore

logger = logging.getLogger(__name__)
PACKAGE_REFERENCE = re.compile(r"usr_[0-9a-f]{32}/[0-9a-f]{32}")


class PackageCleanup:
    def __init__(self, engine: Engine, package_store: PublishedPackageStore):
        self.engine = engine
        self.package_store = package_store

    @staticmethod
    def enqueue(db: Connection, reference: str) -> None:
        if not PACKAGE_REFERENCE.fullmatch(reference):
            raise ValueError("invalid package cleanup reference")
        db.execute(text("""INSERT INTO package_cleanup_queue (package_ref,created_order)
            VALUES (:ref,:created) ON CONFLICT(package_ref) DO NOTHING"""),
            {"ref": reference, "created": time.time_ns()})

    def pending(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("cleanup limit must be between 1 and 1000")
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(text("""SELECT * FROM package_cleanup_queue
                ORDER BY created_order,package_ref LIMIT :limit"""), {"limit": limit}).mappings()]

    def retry(self, reference: str | None = None, *, limit: int = 100) -> list[dict]:
        references = ([reference] if reference is not None else
                      [row["package_ref"] for row in self.pending(limit)])
        results = []
        for package_ref in references:
            if not PACKAGE_REFERENCE.fullmatch(package_ref):
                raise ValueError("invalid package cleanup reference")
            with self.engine.begin() as db:
                # DML acquires SQLite's write lock and the PostgreSQL queue-row
                # lock. Concurrent cleaners cannot operate on this intent twice.
                changed = db.execute(text("""UPDATE package_cleanup_queue SET attempts=attempts+1
                    WHERE package_ref=:ref"""), {"ref": package_ref})
                if changed.rowcount != 1:
                    continue
                if db.execute(text("""SELECT 1 FROM user_scenario_versions
                    WHERE package_ref=:ref LIMIT 1"""), {"ref": package_ref}).first():
                    status, error = "referenced", "package is still referenced by a version"
                else:
                    try:
                        self.package_store.remove(package_ref)
                    except OSError as cause:
                        status, error = "retry_pending", type(cause).__name__
                        logger.warning("package cleanup deferred: %s (%s)", package_ref, error)
                    else:
                        status, error = "removed", None
                if status == "removed":
                    db.execute(text("DELETE FROM package_cleanup_queue WHERE package_ref=:ref"),
                               {"ref": package_ref})
                else:
                    db.execute(text("""UPDATE package_cleanup_queue SET last_error=:error
                        WHERE package_ref=:ref"""), {"error": error, "ref": package_ref})
                results.append({"package_ref": package_ref, "status": status})
        return results


def inspect_local_packages(engine: Engine, directory: str | Path) -> dict:
    """Read-only inventory: untracked packages can include in-flight uploads."""
    root = Path(directory).resolve()
    with engine.connect() as db:
        references = set(db.execute(text("SELECT package_ref FROM user_scenario_versions")).scalars())
    valid = {ref for ref in references if PACKAGE_REFERENCE.fullmatch(ref)}
    on_disk = {path.relative_to(root).as_posix() for path in root.glob("usr_*/*")
               if path.is_dir() and PACKAGE_REFERENCE.fullmatch(path.relative_to(root).as_posix())}
    return {"missing_manifests": sorted(ref for ref in valid if not (root / ref / "manifest.json").is_file()),
            "untracked_packages": sorted(on_disk - references),
            "invalid_references": sorted(references - valid)}
