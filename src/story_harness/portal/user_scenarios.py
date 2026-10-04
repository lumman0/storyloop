"""Validate and publish owner-only uploaded scenario packages."""

from __future__ import annotations

import io
import logging
import re
import shutil
import stat
import time
import zipfile
from pathlib import Path
from typing import Callable
from uuid import uuid4

from sqlalchemy import Engine, text

from story_harness.portal.catalog import GameCatalog, GameListing, _package_fingerprint
from story_harness.portal.scenario_storage import LocalPublishedPackageStore, PublishedPackageStore
from story_harness.runtime.campaign import CampaignProgram
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.prologue import save_prologue


MAX_ARCHIVE_BYTES = 4 * 1024 * 1024
MAX_UNPACKED_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 16
MAX_SCENARIOS_PER_AUTHOR = 20
logger = logging.getLogger(__name__)


class _OneScenarioSource:
    def __init__(self, item: dict) -> None:
        self.item = item

    def games(self) -> list[dict]:
        return [self.item]


def _extract_package(archive: bytes, directory: Path) -> None:
    if not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP file must be between 1 byte and 4 MiB")
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as error:
        raise ValueError("file must be a valid ZIP package") from error
    with bundle:
        files = [info for info in bundle.infolist() if not info.is_dir()]
        if not files or len(files) > MAX_FILES or len(files) != len(bundle.infolist()):
            raise ValueError("ZIP must contain 1–16 JSON files at its root")
        names: set[str] = set()
        total = 0
        for info in files:
            name = info.filename
            file_type = (info.external_attr >> 16) & 0o170000
            base = name.rsplit(".", 1)[0].upper()
            if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.json", name)
                    or base in {"CON", "PRN", "AUX", "NUL"}
                    or re.fullmatch(r"(?:COM|LPT)[1-9]", base)
                    or name in names
                    or file_type not in {0, stat.S_IFREG} or info.flag_bits & 1):
                raise ValueError("ZIP contains an unsafe or duplicate file name")
            names.add(name)
            total += info.file_size
            if info.file_size > MAX_FILE_BYTES or total > MAX_UNPACKED_BYTES:
                raise ValueError("ZIP uncompressed content exceeds the 8 MiB limit")
        if "manifest.json" not in names:
            raise ValueError("ZIP requires manifest.json at its root")
        for info in files:
            try:
                with bundle.open(info) as source:
                    content = source.read(MAX_FILE_BYTES + 1)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise ValueError("ZIP file could not be read") from error
            if len(content) != info.file_size or len(content) > MAX_FILE_BYTES:
                raise ValueError("ZIP file size does not match its declaration")
            (directory / info.filename).write_bytes(content)


class UserScenarioService:
    def __init__(self, engine: Engine, directory: str | Path,
                 package_store: PublishedPackageStore | None = None,
                 prologue_generator: Callable[[ScenarioPackage, CampaignProgram | None, str, str], str]
                 | None = None) -> None:
        self.engine = engine
        self.directory = Path(directory).resolve()
        self.package_store = package_store or LocalPublishedPackageStore(self.directory)
        self.prologue_generator = prologue_generator

    def _prepare_prologue(self, staged: Path, package: ScenarioPackage,
                          program: CampaignProgram | None, title: str,
                          summary: str) -> ScenarioPackage:
        if package.story_blueprint is not None:
            return package
        if package.authored_prologue:
            return package
        if self.prologue_generator is None:
            raise ValueError("scenario prologue generator is unavailable")
        prose = self.prologue_generator(package, program, title, summary).strip()
        return save_prologue(staged, prose)

    @staticmethod
    def _public_row(row) -> dict:
        return {"id": row["scenario_id"], "title": row["title"], "summary": row["summary"],
                "mode": row["mode"], "status": "published" if row["published_version_id"] else "draft",
                "package_version": row["package_version"], "created_at": row["created_at"],
                "version_id": row["version_id"], "review_status": row["review_status"],
                "submission_id": row["submission_id"], "review_reason": row["review_reason"],
                "public_state": row["public_state"]}

    def upload(self, owner_id: str, title: str, summary: str, archive: bytes) -> dict:
        title = title.strip() if isinstance(title, str) else ""
        summary = summary.strip() if isinstance(summary, str) else ""
        if not title or len(title) > 80 or len(summary) > 300:
            raise ValueError("title must have 1–80 characters and summary at most 300")
        with self.engine.connect() as db:
            if db.execute(text("SELECT COUNT(*) FROM user_scenarios WHERE owner_id=:owner"),
                          {"owner": owner_id}).scalar_one() >= MAX_SCENARIOS_PER_AUTHOR:
                raise ValueError("author scenario limit reached")
        scenario_id = f"usr_{uuid4().hex}"
        version_id = uuid4().hex
        reference = f"{scenario_id}/{version_id}"
        staged = self.directory / ".staging" / version_id
        staged.mkdir(parents=True, exist_ok=False)
        package_written = False
        try:
            _extract_package(archive, staged)
            package = ScenarioPackage.load(staged)
            mode = ("campaign" if package.story_blueprint is not None
                    or (staged / "campaign.json").exists() else "freeform")
            program = None
            if mode == "campaign" and package.story_blueprint is None:
                program = CampaignProgram.load(staged / "campaign.json")
                if (program.program_id, program.ticks_per_day) != (package.package_id, package.ticks_per_day):
                    raise ValueError("campaign does not match scenario")
            package = self._prepare_prologue(staged, package, program, title, summary)
            fingerprint = _package_fingerprint(staged, mode)
            self.package_store.publish(reference, staged)
            package_written = True
            now = int(time.time())
            with self.engine.begin() as db:
                # Lock this author's account row before counting uploads. The no-op update
                # serializes writers on both PostgreSQL and SQLite.
                locked = db.execute(text("""UPDATE player_accounts SET player_id=player_id
                    WHERE player_id=:owner"""), {"owner": owner_id})
                if locked.rowcount != 1:
                    raise PermissionError("author account not found")
                count = db.execute(text("SELECT COUNT(*) FROM user_scenarios WHERE owner_id=:owner"),
                                   {"owner": owner_id}).scalar_one()
                if count >= MAX_SCENARIOS_PER_AUTHOR:
                    raise ValueError("author scenario limit reached")
                db.execute(text("""INSERT INTO user_scenarios
                    (scenario_id,owner_id,title,summary,mode,visibility,created_at)
                    VALUES (:id,:owner,:title,:summary,:mode,'private',:created)"""),
                    {"id": scenario_id, "owner": owner_id, "title": title, "summary": summary,
                     "mode": mode, "created": now})
                db.execute(text("""INSERT INTO user_scenario_versions
                    (version_id,scenario_id,package_id,package_version,package_hash,package_ref,created_at)
                    VALUES (:version,:id,:package_id,:package_version,:hash,:ref,:created)"""),
                    {"version": version_id, "id": scenario_id, "package_id": package.package_id,
                     "package_version": package.version, "hash": fingerprint,
                     "ref": reference, "created": now})
            return {"id": scenario_id, "title": title, "summary": summary, "mode": mode,
                    "status": "draft", "package_version": package.version, "created_at": now,
                    "version_id": version_id, "review_status": None, "submission_id": None,
                    "review_reason": None, "public_state": None}
        except Exception:
            if package_written:
                self.package_store.remove(reference)
            raise
        finally:
            shutil.rmtree(staged, ignore_errors=True)

    def list_mine(self, owner_id: str) -> list[dict]:
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT s.*,v.version_id,v.package_version,v.published_at,
                r.status AS review_status,r.submission_id,r.reason AS review_reason,
                p.state AS public_state
                FROM user_scenarios s JOIN user_scenario_versions v ON v.scenario_id=s.scenario_id
                LEFT JOIN scenario_submissions r ON r.version_id=v.version_id
                LEFT JOIN scenario_public_releases p ON p.scenario_id=s.scenario_id
                WHERE s.owner_id=:owner ORDER BY s.created_at DESC,s.scenario_id,
                    v.created_at DESC,v.version_id DESC"""),
                {"owner": owner_id}).mappings().all()
        latest: dict[str, dict] = {}
        for row in rows:
            latest.setdefault(row["scenario_id"], self._public_row(row))
        return list(latest.values())

    def publish(self, owner_id: str, scenario_id: str) -> dict:
        with self.engine.begin() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": scenario_id}).mappings().first()
            if scenario is None:
                raise KeyError("scenario not found")
            if scenario["owner_id"] != owner_id:
                raise PermissionError("scenario belongs to another author")
            version = db.execute(text("""SELECT * FROM user_scenario_versions
                WHERE scenario_id=:id ORDER BY created_at DESC,version_id DESC LIMIT 1"""),
                {"id": scenario_id}).mappings().one()
            self._listing(scenario, version)
            now = int(time.time())
            db.execute(text("""UPDATE user_scenario_versions SET published_at=:now
                WHERE version_id=:version AND published_at IS NULL"""),
                {"now": now, "version": version["version_id"]})
            db.execute(text("""UPDATE user_scenarios SET published_version_id=:version
                WHERE scenario_id=:id"""),
                {"version": version["version_id"], "id": scenario_id})
            return {"id": scenario_id, "title": scenario["title"], "summary": scenario["summary"],
                    "mode": scenario["mode"], "status": "published",
                    "package_version": version["package_version"], "created_at": scenario["created_at"],
                    "version_id": version["version_id"], "review_status": None,
                    "submission_id": None, "review_reason": None, "public_state": None}

    def upload_version(self, owner_id: str, scenario_id: str, title: str,
                       summary: str, archive: bytes) -> dict:
        title = title.strip() if isinstance(title, str) else ""
        summary = summary.strip() if isinstance(summary, str) else ""
        if not title or len(title) > 80 or len(summary) > 300:
            raise ValueError("title must have 1–80 characters and summary at most 300")
        version_id = uuid4().hex
        reference = f"{scenario_id}/{version_id}"
        staged = self.directory / ".staging" / version_id
        staged.mkdir(parents=True, exist_ok=False)
        package_written = False
        try:
            _extract_package(archive, staged)
            package = ScenarioPackage.load(staged)
            mode = ("campaign" if package.story_blueprint is not None
                    or (staged / "campaign.json").exists() else "freeform")
            program = None
            if mode == "campaign" and package.story_blueprint is None:
                program = CampaignProgram.load(staged / "campaign.json")
                if (program.program_id, program.ticks_per_day) != (package.package_id, package.ticks_per_day):
                    raise ValueError("campaign does not match scenario")
            with self.engine.connect() as db:
                row = db.execute(text("""SELECT s.owner_id,s.mode,v.package_id
                    FROM user_scenarios s JOIN user_scenario_versions v
                    ON v.scenario_id=s.scenario_id WHERE s.scenario_id=:id
                    ORDER BY v.created_at,v.version_id LIMIT 1"""), {"id": scenario_id}).mappings().first()
            if row is None:
                raise KeyError("scenario not found")
            if row["owner_id"] != owner_id:
                raise PermissionError("scenario belongs to another author")
            if row["mode"] != mode or row["package_id"] != package.package_id:
                raise ValueError("new version must keep scenario mode and package ID")
            package = self._prepare_prologue(staged, package, program, title, summary)
            fingerprint = _package_fingerprint(staged, mode)
            self.package_store.publish(reference, staged)
            package_written = True
            with self.engine.begin() as db:
                db.execute(text("""UPDATE user_scenarios SET title=:title,summary=:summary
                    WHERE scenario_id=:id AND owner_id=:owner"""),
                    {"title": title, "summary": summary, "id": scenario_id, "owner": owner_id})
                db.execute(text("""INSERT INTO user_scenario_versions
                    (version_id,scenario_id,package_id,package_version,package_hash,package_ref,created_at)
                    VALUES (:version,:id,:package_id,:package_version,:hash,:ref,:created)"""),
                    {"version": version_id, "id": scenario_id, "package_id": package.package_id,
                     "package_version": package.version, "hash": fingerprint,
                     "ref": reference, "created": time.time_ns()})
            return next(item for item in self.list_mine(owner_id) if item["id"] == scenario_id)
        except Exception:
            if package_written:
                self.package_store.remove(reference)
            raise
        finally:
            shutil.rmtree(staged, ignore_errors=True)

    def delete_draft(self, owner_id: str, scenario_id: str) -> dict:
        with self.engine.begin() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": scenario_id}).mappings().first()
            if scenario is None:
                raise KeyError("scenario not found")
            if scenario["owner_id"] != owner_id:
                raise PermissionError("scenario belongs to another author")
            if scenario["published_version_id"] is not None:
                raise ValueError("published scenario cannot be deleted")
            if db.execute(text("SELECT 1 FROM scenario_submissions WHERE scenario_id=:id LIMIT 1"),
                          {"id": scenario_id}).first():
                raise ValueError("submitted scenario cannot be deleted")
            versions = db.execute(text("""SELECT package_ref FROM user_scenario_versions
                WHERE scenario_id=:id"""), {"id": scenario_id}).mappings().all()
            db.execute(text("DELETE FROM user_scenario_versions WHERE scenario_id=:id"),
                       {"id": scenario_id})
            db.execute(text("DELETE FROM user_scenarios WHERE scenario_id=:id"),
                       {"id": scenario_id})
        for version in versions:
            try:
                self.package_store.remove(version["package_ref"])
            except OSError:
                logger.warning("orphaned draft package after metadata deletion: %s",
                               version["package_ref"], exc_info=True)
        return {"status": "deleted"}

    def _listing(self, scenario, version, *, title: str | None = None,
                 summary: str | None = None) -> GameListing:
        entry = {"id": scenario["scenario_id"], "title": title or scenario["title"],
                 "summary": summary if summary is not None else scenario["summary"], "mode": scenario["mode"],
                 "genre": "我的剧本", "package": version["package_ref"]}
        listing = GameCatalog.from_sources(_OneScenarioSource(entry), self.package_store).get(entry["id"])
        if (listing.package_id, listing.package_version, listing.fingerprint) != (
                version["package_id"], version["package_version"], version["package_hash"]):
            raise ValueError("published scenario package changed")
        return listing

    def list_playable(self, owner_id: str) -> tuple[GameListing, ...]:
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT s.*,v.version_id,v.package_id,v.package_version,
                v.package_hash,v.package_ref FROM user_scenarios s
                JOIN user_scenario_versions v ON v.version_id=s.published_version_id
                WHERE s.owner_id=:owner AND s.visibility='private' ORDER BY s.created_at"""),
                {"owner": owner_id}).mappings().all()
        return tuple(self._listing(row, row) for row in rows)

    def get_listing(self, owner_id: str, scenario_id: str,
                    package_hash: str | None = None) -> GameListing:
        with self.engine.connect() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": scenario_id}).mappings().first()
            if scenario is None:
                raise KeyError("scenario not found")
            if scenario["owner_id"] != owner_id:
                raise PermissionError("scenario belongs to another author")
            if package_hash is None:
                version = db.execute(text("""SELECT * FROM user_scenario_versions
                    WHERE version_id=:version AND published_at IS NOT NULL"""),
                    {"version": scenario["published_version_id"]}).mappings().first()
            else:
                version = db.execute(text("""SELECT * FROM user_scenario_versions
                    WHERE scenario_id=:id AND package_hash=:hash AND published_at IS NOT NULL"""),
                    {"id": scenario_id, "hash": package_hash}).mappings().first()
        if version is None:
            raise KeyError("published scenario not found")
        return self._listing(scenario, version)
