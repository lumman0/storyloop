"""Human review of immutable user scenario versions and public releases."""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, text

from story_harness.portal.access import AccessDenied, AccessService, audit
from story_harness.portal.catalog import GameListing
from story_harness.portal.user_scenarios import UserScenarioService


class ScenarioModerationService:
    def __init__(self, engine: Engine, scenarios: UserScenarioService,
                 access: AccessService) -> None:
        self.engine = engine
        self.scenarios = scenarios
        self.access = access

    def submit(self, author_id: str, scenario_id: str) -> dict:
        with self.engine.begin() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": scenario_id}).mappings().first()
            if scenario is None:
                raise KeyError("scenario not found")
            if scenario["owner_id"] != author_id:
                raise PermissionError("scenario belongs to another author")
            version = db.execute(text("""SELECT * FROM user_scenario_versions
                WHERE scenario_id=:id ORDER BY created_at DESC,version_id DESC LIMIT 1"""),
                {"id": scenario_id}).mappings().one()
            self.scenarios._listing(scenario, version)
            existing = db.execute(text("""SELECT 1 FROM scenario_submissions
                WHERE version_id=:version"""), {"version": version["version_id"]}).first()
            if existing:
                raise ValueError("this version has already been submitted; upload a new version")
            pending = db.execute(text("""SELECT 1 FROM scenario_submissions
                WHERE scenario_id=:scenario AND status='pending'"""),
                {"scenario": scenario_id}).first()
            if pending:
                raise ValueError("this scenario already has a pending submission")
            submission_id = uuid4().hex
            now = int(time.time())
            db.execute(text("""INSERT INTO scenario_submissions
                (submission_id,scenario_id,version_id,author_id,package_hash,title,summary,
                 status,submitted_at)
                VALUES (:id,:scenario,:version,:author,:hash,:title,:summary,'pending',:now)"""),
                {"id": submission_id, "scenario": scenario_id,
                 "version": version["version_id"], "author": author_id,
                 "hash": version["package_hash"], "title": scenario["title"],
                 "summary": scenario["summary"], "now": now})
            audit(db, author_id, "scenario.submit", "submission", submission_id,
                  {"scenario_id": scenario_id, "version_id": version["version_id"],
                   "package_hash": version["package_hash"]})
        return self.submission(author_id, submission_id)

    def submission(self, viewer_id: str, submission_id: str) -> dict:
        with self.engine.connect() as db:
            row = db.execute(text("""SELECT r.*,s.mode,v.package_version
                FROM scenario_submissions r JOIN user_scenarios s ON s.scenario_id=r.scenario_id
                JOIN user_scenario_versions v ON v.version_id=r.version_id
                WHERE r.submission_id=:id"""), {"id": submission_id}).mappings().first()
        if row is None:
            raise KeyError("submission not found")
        if viewer_id != row["author_id"]:
            self.access.require(viewer_id, "review.submissions")
        return dict(row)

    def list_mine(self, author_id: str) -> list[dict]:
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT r.*,s.mode,v.package_version
                FROM scenario_submissions r JOIN user_scenarios s ON s.scenario_id=r.scenario_id
                JOIN user_scenario_versions v ON v.version_id=r.version_id
                WHERE r.author_id=:author ORDER BY r.submitted_at DESC,r.submission_id DESC"""),
                {"author": author_id}).mappings().all()
        return [dict(row) for row in rows]

    def withdraw(self, author_id: str, submission_id: str) -> dict:
        with self.engine.begin() as db:
            result = db.execute(text("""UPDATE scenario_submissions SET status='withdrawn',
                decided_at=:now WHERE submission_id=:id AND author_id=:author AND status='pending'"""),
                {"id": submission_id, "author": author_id, "now": int(time.time())})
            if result.rowcount != 1:
                raise ValueError("pending submission not found")
            audit(db, author_id, "scenario.withdraw", "submission", submission_id)
        return self.submission(author_id, submission_id)

    def queue(self, reviewer_id: str, status: str = "pending") -> list[dict]:
        self.access.require(reviewer_id, "review.submissions")
        if status not in {"pending", "approved", "rejected", "withdrawn"}:
            raise ValueError("invalid review status")
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT r.*,s.mode,v.package_version,a.username AS author_name
                FROM scenario_submissions r JOIN user_scenarios s ON s.scenario_id=r.scenario_id
                JOIN user_scenario_versions v ON v.version_id=r.version_id
                JOIN player_accounts a ON a.player_id=r.author_id
                WHERE r.status=:status ORDER BY r.submitted_at,r.submission_id LIMIT 100"""),
                {"status": status}).mappings().all()
        return [dict(row) for row in rows]

    def detail(self, reviewer_id: str, submission_id: str) -> dict:
        self.access.require(reviewer_id, "review.submissions")
        row = self.submission(reviewer_id, submission_id)
        with self.engine.connect() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": row["scenario_id"]}).mappings().one()
            version = db.execute(text("SELECT * FROM user_scenario_versions WHERE version_id=:id"),
                                 {"id": row["version_id"]}).mappings().one()
        listing = self.scenarios._listing(scenario, version, title=row["title"], summary=row["summary"])
        if listing.fingerprint != row["package_hash"]:
            raise ValueError("reviewed package hash changed")
        root = Path(listing.package_path)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        worldbook = json.loads((root / manifest["worldbook"]).read_text(encoding="utf-8"))
        campaign = (json.loads((root / "campaign.json").read_text(encoding="utf-8"))
                    if listing.mode == "campaign" and (root / "campaign.json").is_file()
                    else None)
        blueprint = (json.loads((root / manifest["story_blueprint"]).read_text(encoding="utf-8"))
                     if isinstance(manifest.get("story_blueprint"), str) else None)
        return {**row, "manifest": manifest, "worldbook": worldbook,
                "campaign": campaign, "story_blueprint": blueprint}

    def preview_listing(self, reviewer_id: str, submission_id: str,
                        package_hash: str | None = None) -> GameListing:
        self.access.require(reviewer_id, "review.submissions")
        row = self.submission(reviewer_id, submission_id)
        if row["status"] != "pending":
            raise ValueError("review preview is only available while pending")
        if package_hash is not None and row["package_hash"] != package_hash:
            raise ValueError("preview package hash changed")
        with self.engine.connect() as db:
            scenario = db.execute(text("SELECT * FROM user_scenarios WHERE scenario_id=:id"),
                                  {"id": row["scenario_id"]}).mappings().one()
            version = db.execute(text("SELECT * FROM user_scenario_versions WHERE version_id=:id"),
                                 {"id": row["version_id"]}).mappings().one()
        return self.scenarios._listing(scenario, version, title=row["title"], summary=row["summary"])

    def record_preview(self, game_id: str, submission_id: str, reviewer_id: str) -> None:
        with self.engine.begin() as db:
            db.execute(text("""INSERT INTO review_preview_saves
                (game_id,submission_id,reviewer_id,created_at)
                VALUES (:game,:submission,:reviewer,:now)"""),
                {"game": game_id, "submission": submission_id, "reviewer": reviewer_id,
                 "now": int(time.time())})

    def preview_for(self, game_id: str, reviewer_id: str) -> str | None:
        with self.engine.connect() as db:
            row = db.execute(text("""SELECT submission_id FROM review_preview_saves
                WHERE game_id=:game AND reviewer_id=:reviewer"""),
                {"game": game_id, "reviewer": reviewer_id}).mappings().first()
        return row["submission_id"] if row else None

    def preview_turn_count(self, game_id: str) -> int:
        with self.engine.connect() as db:
            return int(db.execute(text("SELECT COUNT(*) FROM portal_turns WHERE game_id=:game"),
                                  {"game": game_id}).scalar_one())

    def decide(self, reviewer_id: str, submission_id: str, decision: str,
               reason: str = "") -> dict:
        self.access.require(reviewer_id, "review.decide")
        if decision not in {"approved", "rejected"}:
            raise ValueError("invalid review decision")
        reason = reason.strip()
        if decision == "rejected" and not reason:
            raise ValueError("rejection requires a reason")
        if len(reason) > 1000:
            raise ValueError("review reason is too long")
        row = self.submission(reviewer_id, submission_id)
        if row["author_id"] == reviewer_id:
            if "admin" not in self.access.roles(reviewer_id) or not reason:
                raise AccessDenied("self-review requires an administrator override and reason")
        self.detail(reviewer_id, submission_id)
        with self.engine.begin() as db:
            result = db.execute(text("""UPDATE scenario_submissions SET status=:decision,
                reviewer_id=:reviewer,reason=:reason,decided_at=:now
                WHERE submission_id=:id AND status='pending' AND package_hash=:hash"""),
                {"decision": decision, "reviewer": reviewer_id, "reason": reason,
                 "now": int(time.time()), "id": submission_id, "hash": row["package_hash"]})
            if result.rowcount != 1:
                raise ValueError("submission was already decided")
            if decision == "approved":
                db.execute(text("""INSERT INTO scenario_public_releases
                    (scenario_id,version_id,submission_id,state,updated_at,updated_by)
                    VALUES (:scenario,:version,:submission,'active',:now,:reviewer)
                    ON CONFLICT (scenario_id) DO UPDATE SET version_id=:version,
                    submission_id=:submission,state='active',updated_at=:now,updated_by=:reviewer"""),
                    {"scenario": row["scenario_id"], "version": row["version_id"],
                     "submission": submission_id, "now": int(time.time()),
                     "reviewer": reviewer_id})
            audit(db, reviewer_id, "scenario." + decision, "submission", submission_id,
                  {"reason": reason, "scenario_id": row["scenario_id"],
                   "version_id": row["version_id"], "package_hash": row["package_hash"]})
        return self.submission(reviewer_id, submission_id)

    def set_release_state(self, admin_id: str, scenario_id: str, state: str,
                          reason: str) -> dict:
        self.access.require(admin_id, "releases.manage")
        if state not in {"active", "retired", "blocked"}:
            raise ValueError("invalid release state")
        reason = reason.strip()
        if state == "blocked" and not reason:
            raise ValueError("blocking a release requires a reason")
        with self.engine.begin() as db:
            result = db.execute(text("""UPDATE scenario_public_releases
                SET state=:state,updated_at=:now,updated_by=:admin WHERE scenario_id=:scenario"""),
                {"state": state, "now": int(time.time()), "admin": admin_id,
                 "scenario": scenario_id})
            if result.rowcount != 1:
                raise KeyError("public release not found")
            audit(db, admin_id, "release." + state, "scenario", scenario_id,
                  {"reason": reason})
        return {"scenario_id": scenario_id, "state": state}

    def public_listings(self) -> tuple[GameListing, ...]:
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT s.*,v.version_id,v.package_id,v.package_version,
                v.package_hash,v.package_ref,r.title AS reviewed_title,r.summary AS reviewed_summary
                FROM scenario_public_releases p
                JOIN user_scenarios s ON s.scenario_id=p.scenario_id
                JOIN user_scenario_versions v ON v.version_id=p.version_id
                JOIN scenario_submissions r ON r.submission_id=p.submission_id
                WHERE p.state='active' ORDER BY p.updated_at DESC""")).mappings().all()
        return tuple(self.scenarios._listing(row, row, title=row["reviewed_title"],
                                             summary=row["reviewed_summary"]) for row in rows)

    def public_listing(self, scenario_id: str,
                       package_hash: str | None = None) -> GameListing:
        with self.engine.connect() as db:
            release = db.execute(text("""SELECT * FROM scenario_public_releases
                WHERE scenario_id=:id"""), {"id": scenario_id}).mappings().first()
            if release is None or release["state"] == "blocked":
                raise KeyError("public scenario not found")
            if package_hash is None and release["state"] != "active":
                raise KeyError("public scenario not available for new saves")
            if package_hash is None:
                submission_id = release["submission_id"]
            else:
                approved = db.execute(text("""SELECT submission_id FROM scenario_submissions
                    WHERE scenario_id=:id AND package_hash=:hash AND status='approved'
                    ORDER BY decided_at DESC LIMIT 1"""),
                    {"id": scenario_id, "hash": package_hash}).mappings().first()
                if approved is None:
                    raise KeyError("approved scenario version not found")
                submission_id = approved["submission_id"]
            row = db.execute(text("""SELECT s.*,v.version_id,v.package_id,v.package_version,
                v.package_hash,v.package_ref,r.title AS reviewed_title,r.summary AS reviewed_summary
                FROM scenario_submissions r JOIN user_scenarios s ON s.scenario_id=r.scenario_id
                JOIN user_scenario_versions v ON v.version_id=r.version_id
                WHERE r.submission_id=:id"""), {"id": submission_id}).mappings().one()
        return self.scenarios._listing(row, row, title=row["reviewed_title"],
                                       summary=row["reviewed_summary"])

    def releases(self, admin_id: str) -> list[dict]:
        self.access.require(admin_id, "releases.manage")
        with self.engine.connect() as db:
            rows = db.execute(text("""SELECT p.*,r.title,r.summary FROM scenario_public_releases p
                JOIN scenario_submissions r ON r.submission_id=p.submission_id
                ORDER BY p.updated_at DESC LIMIT 100""")).mappings().all()
        return [dict(row) for row in rows]
