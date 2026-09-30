"""Authenticated player entry points around the existing story harness."""

from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.adapters.telemetry import configured_telemetry
from story_harness.portal.catalog import GameCatalog, GameListing
from story_harness.portal.repository import PlayerRepository, SaveRecord
from story_harness.portal.sql_repository import SQLPlayerRepository
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.game_session import GameSession
from story_harness.runtime.guidance import GuidanceAdvisor, GuidanceResult
from story_harness.runtime.react_factory import make_react_session
from story_harness.world.scenario import ScenarioPackage


class PlayerPortal:
    """Identity and save ownership stay outside scenario and agent contexts."""

    def __init__(self, catalog_path: str | Path, config_path: str | Path,
                 db_path: str | None = None,
                 accounts: PlayerRepository | None = None) -> None:
        self.catalog = GameCatalog.load(catalog_path)
        self.config = HarnessConfig.load(config_path)
        self.config.allowed_hosts()
        if self.config.profile == "online":
            self._require_model_key()
        self.db_path = db_path or self.config.storage.path
        self.engine = self.config.create_database(db_path)
        self.store = self.config.create_store(engine=self.engine)
        self.accounts = accounts or SQLPlayerRepository(self.engine)
        self.telemetry = configured_telemetry()
        self._react_sessions: dict[Path, GameSession] = {}
        self._campaign_sessions: dict[Path, tuple[CampaignProgram, CampaignSession]] = {}

    def close(self) -> None:
        self.telemetry.flush()
        self.engine.dispose()

    def register(self, username: str, password: str) -> dict:
        player_id = self.accounts.register(username, password)
        return {"player_id": player_id, "token": self.accounts.issue_token(player_id)}

    def login(self, username: str, password: str) -> dict:
        player_id = self.accounts.authenticate(username, password)
        return {"player_id": player_id, "token": self.accounts.issue_token(player_id)}

    def logout(self, token: str) -> None:
        self.accounts.resolve_token(token)
        self.accounts.revoke_token(token)

    def games(self, token: str) -> list[dict]:
        self.accounts.resolve_token(token)
        return [{"id": item.game_id, "title": item.title, "mode": item.mode,
                 "summary": item.summary, "genre": item.genre, "theme": item.theme}
                for item in self.catalog.list_games()]

    def history(self, token: str, game_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        intro = self.accounts.get_intro(game_id)
        if intro is None:
            package = ScenarioPackage.load(item.package_path)
            intro = self._view(game_id, item.game_id, item.mode, "", self.store.load(game_id),
                               guidance=GuidanceResult((), "history_fallback"),
                               opening=package.opening)
        return {"game_id": game_id, "intro": intro, "turns": self.accounts.list_turns(game_id)}

    def saves(self, token: str) -> list[dict]:
        player_id = self.accounts.resolve_token(token)
        result = []
        for record in self.accounts.list_saves(player_id):
            try:
                item = self._verified_listing(record)
            except (KeyError, ValueError):
                item = None
            snapshot = self.store.load(record.game_id)
            campaign = snapshot.data.get("campaign")
            result.append({"game_id": record.game_id, "catalog_id": record.catalog_id,
                           "title": item.title if item else record.catalog_id,
                           "mode": item.mode if item else None, "available": item is not None,
                           "tick": snapshot.tick,
                           "day": campaign.get("day") if isinstance(campaign, dict) else None,
                           "complete": bool(campaign.get("ending")) if isinstance(campaign, dict) else False})
        return result

    def _verified_listing(self, record: SaveRecord) -> GameListing:
        item = self.catalog.get(record.catalog_id)
        if ((item.package_id, item.package_version, item.fingerprint)
                != (record.package_id, record.package_version, record.package_hash)):
            raise ValueError("scenario package changed; this save needs an explicit migration")
        return item

    def _react(self, item: GameListing, package: ScenarioPackage) -> GameSession:
        key = item.package_path
        if key in self._react_sessions:
            return self._react_sessions[key]
        values = dict(os.environ)
        self._require_model_key(values)
        session = make_react_session(self.config, package, self.store, values, self.telemetry)
        self._react_sessions[key] = session
        return session

    def _require_model_key(self, values: dict[str, str] | None = None) -> None:
        if not (values or os.environ).get(self.config.api_key_env):
            raise ValueError(f"set {self.config.api_key_env} before starting a game")

    def _campaign(self, item: GameListing, package: ScenarioPackage) -> tuple[CampaignProgram, CampaignSession]:
        key = item.package_path
        if key in self._campaign_sessions:
            return self._campaign_sessions[key]
        program = CampaignProgram.load(item.package_path / "campaign.json")
        result = (program, CampaignSession(self.store, program, self._react(item, package), telemetry=self.telemetry))
        self._campaign_sessions[key] = result
        return result

    @staticmethod
    def _view(game_id: str, catalog_id: str, mode: str, body: str,
              snapshot, guidance, *, complete: bool = False,
              opening: str = "", turn_id: str | None = None) -> dict:
        campaign = snapshot.data.get("campaign")
        return {"game_id": game_id, "catalog_id": catalog_id, "mode": mode,
                "opening": opening, "body": body, "suggestions": list(guidance.items),
                "tick": snapshot.tick, "state_version": snapshot.version,
                "day": campaign.get("day") if isinstance(campaign, dict) else None,
                "complete": complete, "turn_id": turn_id}

    async def create_save(self, token: str, catalog_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        item = self.catalog.get(catalog_id)
        self._require_model_key()
        package = ScenarioPackage.load(item.package_path)
        game_id = uuid4().hex
        package.seed_game(self.store, game_id)
        self.accounts.create_save(player_id, item.game_id, game_id,
                                  item.package_id, item.package_version, item.fingerprint)
        result = await self._open_save(item, package, game_id, opening=package.opening)
        self.accounts.store_intro(game_id, result)
        return result

    async def resume_save(self, token: str, game_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        latest = self.accounts.latest_turn_response(game_id)
        snapshot = self.store.load(game_id)
        if (latest is not None and snapshot.version == latest["state_version"]
                and not self.store.ready_work(game_id, snapshot.tick)):
            return {**latest, "opening": ""}
        package = ScenarioPackage.load(item.package_path)
        result = await self._open_save(item, package, game_id,
                                       opening=package.opening if latest is None else "")
        if latest is None:
            self.accounts.store_intro(game_id, result)
        return result

    async def _open_save(self, item: GameListing, package: ScenarioPackage,
                         game_id: str, opening: str = "") -> dict:
        if item.mode == "campaign":
            program, session = self._campaign(item, package)
            outcome = await session.start(game_id)
            guidance = await GuidanceAdvisor(self.store, package, program,
                                             telemetry=self.telemetry).advise(
                game_id, outcome.snapshot, gate_id=outcome.gate_id,
                complete=outcome.complete, visible_text=outcome.text)
            return self._view(game_id, item.game_id, item.mode, outcome.text,
                              outcome.snapshot, guidance, complete=outcome.complete,
                              opening=opening)
        snapshot = self.store.load(game_id)
        guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
            game_id, snapshot, visible_text=opening)
        return self._view(game_id, item.game_id, item.mode, "", snapshot, guidance,
                          opening=opening)

    async def turn(self, token: str, game_id: str, text: str,
                   request_id: str | None = None) -> dict:
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("turn text is required")
        if len(text) > 10_000:
            raise ValueError("turn text is too long")
        request_id = request_id or uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            raise ValueError("request_id must contain 1–64 URL-safe characters")
        cached = self.accounts.get_turn_response(game_id, request_id, text)
        if cached is not None:
            return cached
        package = ScenarioPackage.load(item.package_path)
        turn_id = f"portal-{request_id}"
        if item.mode == "freeform":
            recovered = await self._recover_freeform(item, package, game_id, text, turn_id)
            if recovered is not None:
                self.accounts.store_turn_response(game_id, request_id, text, recovered)
                return recovered
        if item.mode == "campaign":
            program, session = self._campaign(item, package)
            outcome = await session.submit(game_id, text, turn_id)
            guidance = await GuidanceAdvisor(self.store, package, program,
                                             telemetry=self.telemetry).advise(
                game_id, outcome.snapshot, gate_id=outcome.gate_id,
                complete=outcome.complete, visible_text=outcome.text)
            view = self._view(game_id, item.game_id, item.mode, outcome.text,
                              outcome.snapshot, guidance, complete=outcome.complete,
                              turn_id=turn_id)
        else:
            outcome = await self._react(item, package).run_turn(game_id, text, turn_id)
            guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
                game_id, outcome.snapshot, visible_text=outcome.narration)
            view = self._view(game_id, item.game_id, item.mode, outcome.narration,
                              outcome.snapshot, guidance, turn_id=turn_id)
        self.accounts.store_turn_response(game_id, request_id, text, view)
        return view

    async def _recover_freeform(self, item: GameListing, package: ScenarioPackage,
                                game_id: str, text: str, turn_id: str) -> dict | None:
        committed = next(((kind, self.store.event_details(game_id, f"{turn_id}:{kind}"))
                          for kind in ("input", "query", "action")
                          if self.store.event_exists(game_id, f"{turn_id}:{kind}")), None)
        if committed is None:
            return None
        kind, details = committed
        if details is None or details.get("text") != text:
            raise ValueError("request ID already belongs to different input")
        history = self.store.player_inputs_for(game_id)
        if not history or history[-1].event_id != f"{turn_id}:{kind}":
            raise ValueError("a later turn has already started; resume the saved game")
        await self._react(item, package).run_ready_work(game_id)
        snapshot = self.store.load(game_id)
        visible = [observation.content for observation in self.store.observations_for(game_id, "player")
                   if observation.event_id.startswith(f"{turn_id}:")]
        body = "\n\n".join(visible) or "上次操作已提交，暂时没有新的可见变化。"
        guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
            game_id, snapshot, visible_text=body)
        return self._view(game_id, item.game_id, item.mode, body, snapshot, guidance,
                          turn_id=turn_id)
