"""Authenticated player entry points around the existing story harness."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4
from weakref import WeakValueDictionary

from story_harness.adapters.runtime_config import HarnessConfig
from story_harness.adapters.telemetry import configured_telemetry, session_id_for_game
from story_harness.agents.scene_narrator import CampaignSceneNarrator
from story_harness.agents.novel_narrator import NovelTurnNarrator
from story_harness.agents.prologue_generator import ModelPrologueGenerator
from story_harness.agents.action_advisor import ActionOption, ActionOptionAdvisor
from story_harness.agents.status_adjudicator import ModelStatusAdjudicator
from story_harness.core.billing import collect_usage
from story_harness.core.contracts import Observation
from story_harness.portal.catalog import GameCatalog, GameListing
from story_harness.portal.access import AccessService
from story_harness.portal.invitations import InvitationService
from story_harness.portal.moderation import ScenarioModerationService
from story_harness.portal.repository import PlayerRepository, SaveRecord
from story_harness.portal.sql_repository import SQLPlayerRepository
from story_harness.portal.save_generation_settings import SaveGenerationSettings, SQLSaveGenerationSettings
from story_harness.portal.player_memory import Mem0PlayerMemory, PlayerMemory
from story_harness.portal.player_memory_jobs import MemoryBatch, SQLPlayerMemoryJobs
from story_harness.portal.sql_billing import SQLBillingRepository
from story_harness.portal.user_scenarios import UserScenarioService
from story_harness.portal.presentation import campaign_interaction
from story_harness.runtime.campaign import CampaignProgram, CampaignSession
from story_harness.runtime.game_session import GameSession
from story_harness.runtime.presentation import StorySegment, segment_for_observation
from story_harness.runtime.novel_presentation import present_freeform_novel
from story_harness.runtime.guidance import GuidanceAdvisor, GuidanceResult
from story_harness.runtime.react_factory import make_react_session
from story_harness.runtime.turn_progress import TurnProgress, emit
from story_harness.runtime.story_clock import StoryClock
from story_harness.runtime.status_update import settle_status
from story_harness.runtime.player_preferences import player_preferences_scope
from story_harness.world.scenario import ScenarioPackage
from story_harness.world.status_fields import StatusField, project_status_fields


class PlayerPortal:
    """Identity and save ownership stay outside scenario and agent contexts."""

    @staticmethod
    def _package_for_mode(package: ScenarioPackage, play_mode: str) -> ScenarioPackage:
        # Delivery belongs to the save, while scenario data remains reusable.
        presentation = "novel" if play_mode == "campaign" else "interactive"
        return replace(package, presentation_mode=presentation)

    def __init__(self, catalog_path: str | Path | None, config_path: str | Path,
                 db_path: str | None = None,
                 accounts: PlayerRepository | None = None,
                 *, catalog: GameCatalog | None = None,
                 prologue_generator=None) -> None:
        if catalog is not None:
            self.catalog = catalog
        elif catalog_path is not None:
            self.catalog = GameCatalog.load(catalog_path)
        else:
            raise ValueError("catalog path or catalog provider is required")
        self.config = HarnessConfig.load(config_path)
        self.config.allowed_hosts()
        if self.config.profile == "online":
            self._require_model_key()
        self.db_path = db_path or self.config.storage.path
        upload_dir = os.environ.get("STORY_UPLOAD_DIR")
        if not upload_dir and self.config.profile == "online":
            raise ValueError("STORY_UPLOAD_DIR is required in online mode")
        if not upload_dir:
            upload_dir = str(Path(self.db_path).resolve().parent / "uploaded-scenarios")
        self.engine = self.config.create_database(db_path)
        self.store = self.config.create_store(engine=self.engine)
        self.accounts = accounts or SQLPlayerRepository(self.engine)
        self.save_generation_settings = SQLSaveGenerationSettings(self.engine)
        self.access = AccessService(self.engine)
        self.invitations = InvitationService(self.engine, self.access)
        self.memory_jobs = SQLPlayerMemoryJobs(self.engine)
        self.memory_feature_enabled = self.config.player_memory_enabled()
        self.player_memory: PlayerMemory | None = (
            Mem0PlayerMemory(self.config, self.config.player_memory_path())
            if self.config.player_memory.driver == "mem0" else None
        )
        self._profile_cache: dict[str, tuple[str, ...]] = {}
        self._memory_access = asyncio.Lock()
        self._memory_wakeup = asyncio.Event()
        self.telemetry = configured_telemetry()
        self.user_scenarios = UserScenarioService(
            self.engine, upload_dir,
            prologue_generator=prologue_generator or self._generate_prologue,
        )
        self.moderation = ScenarioModerationService(self.engine, self.user_scenarios, self.access)
        self.billing = (SQLBillingRepository(self.engine, self.config.billing_policy, self.accounts)
                        if self.config.billing_policy is not None else None)
        self._react_sessions: dict[tuple[Path, str, SaveGenerationSettings], GameSession] = {}
        self._campaign_sessions: dict[tuple[Path, str, SaveGenerationSettings], tuple[CampaignProgram, CampaignSession]] = {}
        self._player_turn_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    def close(self) -> None:
        self.telemetry.flush()
        if self.player_memory is not None:
            self.player_memory.close()
        self.engine.dispose()

    async def memory_status(self, token: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        available = self.memory_feature_enabled and self.player_memory is not None
        enabled = available and self.memory_jobs.enabled(player_id)
        memories = (await asyncio.to_thread(self.player_memory.list_memories, player_id)
                    if self.player_memory is not None else [])
        return {"available": available, "enabled": enabled, "memories": memories,
                "queued_inputs": self.memory_jobs.pending_count(player_id),
                "batch_size": 6, "min_interval_hours": 12,
                "charged_points": 0}

    async def set_memory_enabled(self, token: str, enabled: bool) -> dict:
        player_id = self.accounts.resolve_token(token)
        if enabled and not self.memory_feature_enabled:
            raise ValueError("玩家画像尚未由平台开放")
        async with self._memory_access:
            self.memory_jobs.set_enabled(player_id, enabled)
            self._profile_cache.pop(player_id, None)
        return await self.memory_status(token)

    async def clear_memory(self, token: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        if self.player_memory is None:
            raise ValueError("玩家画像当前不可用")
        async with self._memory_access:
            self.memory_jobs.clear(player_id)
            await asyncio.to_thread(self.player_memory.clear, player_id)
            self._profile_cache.pop(player_id, None)
        return await self.memory_status(token)

    async def _preferences_for(self, player_id: str) -> tuple[str, ...]:
        if not self.memory_feature_enabled or self.player_memory is None or not self.memory_jobs.enabled(player_id):
            return ()
        if player_id in self._profile_cache:
            return self._profile_cache[player_id]
        try:
            rows = await asyncio.to_thread(self.player_memory.list_memories, player_id)
            result = tuple(row["text"][:180] for row in rows[:8])
            self._profile_cache[player_id] = result
            return result
        except Exception:
            logging.getLogger(__name__).exception("player profile read failed")
            return ()

    def _queue_memory_input(self, player_id: str, game_id: str,
                            request_id: str, player_text: str) -> None:
        if not self.memory_feature_enabled or self.player_memory is None:
            return
        if player_text == "/continue" or player_text in {"/next", "/rest"} or player_text.startswith("/choose "):
            return
        try:
            if self.memory_jobs.enqueue(player_id, game_id, request_id, player_text):
                self._memory_wakeup.set()
        except Exception:
            logging.getLogger(__name__).exception("player profile enqueue failed")

    async def run_memory_worker(self) -> None:
        if not self.memory_feature_enabled or self.player_memory is None:
            return
        while True:
            task = asyncio.create_task(self._run_memory_batch())
            try:
                batch = await asyncio.shield(task)
            except asyncio.CancelledError:
                # Finish the claimed batch before closing its embedded Qdrant store.
                try:
                    await task
                except Exception:
                    logging.getLogger(__name__).exception("player profile batch failed during shutdown")
                raise
            except Exception:
                logging.getLogger(__name__).exception("player profile worker failed; retrying")
                batch = None
            if batch is None:
                self._memory_wakeup.clear()
                try:
                    await asyncio.wait_for(self._memory_wakeup.wait(), timeout=20)
                except asyncio.TimeoutError:
                    pass

    async def _run_memory_batch(self) -> MemoryBatch | None:
        async with self._memory_access:
            batch = await asyncio.to_thread(self.memory_jobs.claim)
            if batch is None:
                return None
            with self.telemetry.span(
                "player-memory-batch", {"input_count": len(batch.items),
                                        "provider": "mem0", "billed_to_player": False},
                session_id=session_id_for_game(batch.items[0][0]),
            ) as span:
                try:
                    await asyncio.to_thread(
                        self.player_memory.remember, batch.player_id,
                        tuple(item[2] for item in batch.items),
                    )
                except Exception:
                    span.metric("story.player_memory_batch_success", 0.0)
                    logging.getLogger(__name__).exception("player profile extraction failed")
                    await asyncio.to_thread(self.memory_jobs.fail, batch)
                else:
                    await asyncio.to_thread(self.memory_jobs.complete, batch)
                    self._profile_cache.pop(batch.player_id, None)
                    span.metric("story.player_memory_batch_success", 1.0)
            return batch

    def _player_lock(self, player_id: str) -> asyncio.Lock:
        lock = self._player_turn_locks.get(player_id)
        if lock is None:
            lock = asyncio.Lock()
            self._player_turn_locks[player_id] = lock
        return lock

    def register(self, username: str, password: str, invite_code: str | None = None) -> dict:
        player_id = self.accounts.register(username, password, invite_code,
                                           require_invite=self.config.profile == "online")
        if self.billing is not None:
            self.billing.ensure_wallet(player_id)
        return {"player_id": player_id, "token": self.accounts.issue_token(player_id)}

    def login(self, username: str, password: str) -> dict:
        player_id = self.accounts.authenticate(username, password)
        if self.billing is not None:
            self.billing.ensure_wallet(player_id)
        return {"player_id": player_id, "token": self.accounts.issue_token(player_id)}

    def wallet(self, token: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        if self.billing is None:
            raise ValueError("billing is not configured")
        return self.billing.wallet(player_id)

    def credit_ledger(self, token: str, limit: int = 30) -> list[dict]:
        player_id = self.accounts.resolve_token(token)
        if self.billing is None:
            raise ValueError("billing is not configured")
        return self.billing.ledger(player_id, limit)

    def logout(self, token: str) -> None:
        self.accounts.resolve_token(token)
        self.accounts.revoke_token(token)

    def session_info(self, token: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        return {"player_id": player_id, "roles": list(self.access.roles(player_id)),
                "capabilities": list(self.access.capabilities(player_id))}

    def games(self, token: str) -> list[dict]:
        player_id = self.accounts.resolve_token(token)
        listings = {item.game_id: item for item in self.catalog.list_games()}
        listings.update({item.game_id: item for item in self.user_scenarios.list_playable(player_id)})
        listings.update({item.game_id: item for item in self.moderation.public_listings()})
        return [{"id": item.game_id, "title": item.title, "mode": item.mode,
                 "play_modes": list(item.supported_play_modes),
                 "summary": item.summary, "genre": item.genre, "theme": item.theme,
                 "cover_url": (f"/v1/catalog/{quote(item.game_id, safe='')}/artwork/cover"
                               if item.cover_art else None)}
                for item in listings.values()]

    @staticmethod
    def _artwork_path(item: GameListing, relative_path: str) -> Path:
        root = item.package_path.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError("artwork not found")
        return path

    def cover_artwork(self, token: str, catalog_id: str) -> Path:
        player_id = self.accounts.resolve_token(token)
        item = self._listing_for(player_id, catalog_id)
        if not item.cover_art:
            raise KeyError("cover not found")
        return self._artwork_path(item, item.cover_art)

    def cast(self, token: str, game_id: str) -> list[dict]:
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        if not item.portrait_art:
            return []
        package = ScenarioPackage.load(item.package_path)
        snapshot = self.store.load(game_id)
        visible: set[str] = set()
        campaign = snapshot.data.get("campaign")
        if isinstance(campaign, dict):
            met = campaign.get("met", {})
            if isinstance(met, dict):
                visible.update(actor_id for actor_id, known in met.items() if known is True)
            cursor = campaign.get("cursor", 0)
            if type(cursor) is int and cursor > 0:
                program = CampaignProgram.load(item.package_path / "campaign.json")
                for step in program.steps[:cursor]:
                    if step["kind"] == "scene":
                        visible.update(actor_id for actor_id, name in package.actor_names.items()
                                       if name in step["text"])
        for turn in self.accounts.list_turns(game_id):
            for segment in turn["response"].get("segments", ()):
                if segment.get("kind") == "dialogue" and isinstance(segment.get("speaker_id"), str):
                    visible.add(segment["speaker_id"])
        return [{"id": actor_id, "name": package.actor_names[actor_id],
                 "portrait_url": f"/v1/saves/{game_id}/cast/{quote(actor_id, safe='')}/portrait"}
                for actor_id, _ in package.actor_cards
                if actor_id in visible and actor_id in item.portrait_art]

    def portrait_artwork(self, token: str, game_id: str, actor_id: str) -> Path:
        visible = {actor["id"] for actor in self.cast(token, game_id)}
        if actor_id not in visible:
            raise KeyError("portrait not available")
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        return self._artwork_path(item, item.portrait_art[actor_id])

    def upload_scenario(self, token: str, title: str, summary: str, archive: bytes) -> dict:
        player_id = self.accounts.resolve_token(token)
        return self.user_scenarios.upload(player_id, title, summary, archive)

    def _generate_prologue(self, package: ScenarioPackage, program: CampaignProgram | None,
                           title: str, summary: str) -> str:
        task = "prologue" if "prologue" in self.config.task_models else "narration"
        model = self.config.create_model(task, dict(os.environ), self.telemetry)
        return asyncio.run(ModelPrologueGenerator(model, self.telemetry).generate(
            package, program, title, summary,
        ))

    def upload_scenario_version(self, token: str, scenario_id: str, title: str,
                                summary: str, archive: bytes) -> dict:
        player_id = self.accounts.resolve_token(token)
        return self.user_scenarios.upload_version(player_id, scenario_id, title, summary, archive)

    def submit_scenario(self, token: str, scenario_id: str) -> dict:
        return self.moderation.submit(self.accounts.resolve_token(token), scenario_id)

    def my_submissions(self, token: str) -> list[dict]:
        return self.moderation.list_mine(self.accounts.resolve_token(token))

    def withdraw_submission(self, token: str, submission_id: str) -> dict:
        return self.moderation.withdraw(self.accounts.resolve_token(token), submission_id)

    def review_queue(self, token: str, status: str = "pending") -> list[dict]:
        return self.moderation.queue(self.accounts.resolve_token(token), status)

    def review_detail(self, token: str, submission_id: str) -> dict:
        return self.moderation.detail(self.accounts.resolve_token(token), submission_id)

    def review_decide(self, token: str, submission_id: str, decision: str,
                      reason: str = "") -> dict:
        return self.moderation.decide(self.accounts.resolve_token(token), submission_id,
                                      decision, reason)

    async def create_review_preview(self, token: str, submission_id: str) -> dict:
        reviewer_id = self.accounts.resolve_token(token)
        item = self.moderation.preview_listing(reviewer_id, submission_id)
        package = self._package_for_mode(ScenarioPackage.load(item.package_path), item.mode)
        game_id = uuid4().hex
        package.seed_game(self.store, game_id)
        self.accounts.create_save(reviewer_id, item.game_id, game_id,
                                  item.package_id, item.package_version, item.fingerprint)
        self.moderation.record_preview(game_id, submission_id, reviewer_id)
        with player_preferences_scope(()):
            result = await self._open_save(item, package, game_id, opening=package.opening)
        self.accounts.store_intro(game_id, result)
        return result

    def admin_users(self, token: str) -> list[dict]:
        return self.access.list_users(self.accounts.resolve_token(token))

    def admin_issue_invitations(self, token: str, count: int = 1) -> dict:
        return self.invitations.issue(self.accounts.resolve_token(token), count)

    def admin_invitations(self, token: str) -> list[dict]:
        return self.invitations.list_invitations(self.accounts.resolve_token(token))

    def admin_revoke_invitation(self, token: str, invitation_id: str) -> dict:
        return self.invitations.revoke(self.accounts.resolve_token(token), invitation_id)

    def admin_set_role(self, token: str, player_id: str, role: str, enabled: bool) -> dict:
        admin_id = self.accounts.resolve_token(token)
        self.access.set_role(admin_id, player_id, role, enabled)
        return {"player_id": player_id, "roles": list(self.access.roles(player_id))}

    def admin_set_status(self, token: str, player_id: str, status: str) -> dict:
        self.access.set_status(self.accounts.resolve_token(token), player_id, status)
        return {"player_id": player_id, "status": status}

    def admin_releases(self, token: str) -> list[dict]:
        return self.moderation.releases(self.accounts.resolve_token(token))

    def admin_release_state(self, token: str, scenario_id: str,
                            state: str, reason: str) -> dict:
        return self.moderation.set_release_state(self.accounts.resolve_token(token),
                                                 scenario_id, state, reason)

    def admin_audit(self, token: str) -> list[dict]:
        return self.access.list_audit(self.accounts.resolve_token(token))

    def my_scenarios(self, token: str) -> list[dict]:
        player_id = self.accounts.resolve_token(token)
        return self.user_scenarios.list_mine(player_id)

    def publish_scenario(self, token: str, scenario_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        return self.user_scenarios.publish(player_id, scenario_id)

    def delete_scenario_draft(self, token: str, scenario_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        return self.user_scenarios.delete_draft(player_id, scenario_id)

    def _listing_for(self, player_id: str, catalog_id: str,
                     package_hash: str | None = None) -> GameListing:
        try:
            return self.catalog.get(catalog_id)
        except KeyError:
            if catalog_id.startswith("usr_"):
                try:
                    return self.moderation.public_listing(catalog_id, package_hash)
                except KeyError:
                    return self.user_scenarios.get_listing(player_id, catalog_id, package_hash)
            raise

    def history(self, token: str, game_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        intro = self.accounts.get_intro(game_id)
        if intro is None:
            package = ScenarioPackage.load(item.package_path)
            intro = self._view(game_id, item.game_id, record.play_mode or item.mode, "", self.store.load(game_id),
                               guidance=GuidanceResult((), "history_fallback"),
                               opening=package.opening, status_fields=package.status_fields,
                               time_unit=package.time_unit)
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
                           "mode": (record.play_mode or item.mode) if item else record.play_mode,
                           "available": item is not None,
                           "tick": snapshot.tick,
                           "day": campaign.get("day") if isinstance(campaign, dict) else None,
                           "complete": bool(campaign.get("ending")) if isinstance(campaign, dict) else False})
        return result

    def _verified_listing(self, record: SaveRecord) -> GameListing:
        preview_submission = self.moderation.preview_for(record.game_id, record.player_id)
        item = (self.moderation.preview_listing(record.player_id, preview_submission,
                                                record.package_hash)
                if preview_submission else
                self._listing_for(record.player_id, record.catalog_id, record.package_hash))
        if ((item.package_id, item.package_version, item.fingerprint)
                != (record.package_id, record.package_version, record.package_hash)):
            raise ValueError("scenario package changed; this save needs an explicit migration")
        return item

    def _default_generation_settings(self) -> SaveGenerationSettings:
        compression_task = ("context_compression" if "context_compression" in self.config.task_models
                            else "main_react")
        window = min(self.config.context_window_for(task)
                     for task in ("main_react", "npc_reply", compression_task))
        temperature = float(self.config.model_generate_kwargs.get("temperature", 1.0))
        return SaveGenerationSettings(temperature, window)

    def _generation_settings(self, game_id: str) -> SaveGenerationSettings:
        return self.save_generation_settings.get(game_id, self._default_generation_settings())

    def get_save_settings(self, token: str, game_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        self.accounts.get_save(player_id, game_id)
        defaults = self._default_generation_settings()
        settings = self._generation_settings(game_id)
        return {"temperature": settings.temperature,
                "context_window_tokens": settings.context_window_tokens,
                "default_temperature": defaults.temperature,
                "default_context_window_tokens": defaults.context_window_tokens,
                "max_context_window_tokens": defaults.context_window_tokens}

    async def set_save_settings(self, token: str, game_id: str,
                                temperature: float, context_window_tokens: int) -> dict:
        player_id = self.accounts.resolve_token(token)
        async with self._player_lock(player_id):
            self.accounts.get_save(player_id, game_id)
            max_window = self._default_generation_settings().context_window_tokens
            if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
                    or not math.isfinite(temperature) or not 0 <= temperature <= 1.9):
                raise ValueError("temperature must be between 0 and 1.9")
            if (type(context_window_tokens) is not int or
                    not 8192 <= context_window_tokens <= max_window):
                raise ValueError(f"context window must be between 8192 and {max_window} tokens")
            previous = self._generation_settings(game_id)
            settings = SaveGenerationSettings(float(temperature), context_window_tokens)
            self.save_generation_settings.put(game_id, settings, previous)
            for cache in (self._react_sessions, self._campaign_sessions):
                for key in tuple(cache):
                    if key[1] == game_id:
                        del cache[key]
        return self.get_save_settings(token, game_id)

    def _react(self, item: GameListing, package: ScenarioPackage, game_id: str) -> GameSession:
        settings = self._generation_settings(game_id)
        key = (item.package_path, game_id, settings)
        if key in self._react_sessions:
            return self._react_sessions[key]
        values = dict(os.environ)
        self._require_model_key(values)
        clock = (StoryClock(package.ticks_per_day * item.turns_per_story_tick)
                 if package.ticks_per_day is not None else None)
        session = make_react_session(self.config, package, self.store, values, self.telemetry,
                                     story_clock=clock, temperature=settings.temperature,
                                     context_window_tokens=settings.context_window_tokens)
        self._react_sessions[key] = session
        if len(self._react_sessions) > 128:
            self._react_sessions.pop(next(iter(self._react_sessions)))
        return session

    def _require_model_key(self, values: dict[str, str] | None = None) -> None:
        if not self.config.model_api_key(values):
            raise ValueError(f"set {self.config.api_key_env} or configure a local model key file before starting a game")

    def _campaign(self, item: GameListing, package: ScenarioPackage,
                  game_id: str) -> tuple[CampaignProgram, CampaignSession]:
        settings = self._generation_settings(game_id)
        key = (item.package_path, game_id, settings)
        if key in self._campaign_sessions:
            return self._campaign_sessions[key]
        program = CampaignProgram.load(item.package_path / "campaign.json")
        result = (program, CampaignSession(
            self.store, program, self._react(item, package, game_id), telemetry=self.telemetry,
            turns_per_story_tick=item.turns_per_story_tick,
            scene_presenter=CampaignSceneNarrator(
                package, program, self.config.create_model("narration", dict(os.environ), self.telemetry,
                                                           temperature=settings.temperature),
                self.telemetry,
            ) if package.presentation_mode == "interactive" else None,
            novel_presenter=self._novel_presenter(package, game_id) if package.presentation_mode == "novel" else None,
        ))
        self._campaign_sessions[key] = result
        if len(self._campaign_sessions) > 128:
            self._campaign_sessions.pop(next(iter(self._campaign_sessions)))
        return result

    def _novel_presenter(self, package: ScenarioPackage, game_id: str) -> NovelTurnNarrator:
        return NovelTurnNarrator(
            package,
            self.config.create_model("narration", dict(os.environ), self.telemetry,
                                     temperature=self._generation_settings(game_id).temperature),
            self.telemetry,
        )

    async def _action_options(self, body: str, presentation_mode: str, *,
                              game_id: str = "", scenario_id: str = "",
                              gate_id: str | None = None,
                              complete: bool = False,
                              program: CampaignProgram | None = None,
                              snapshot=None) -> tuple[ActionOption, ...]:
        if gate_id is not None or complete or not body.strip():
            return ()
        task = ("followup_actions" if "followup_actions" in self.config.task_models
                else "npc_selection")
        advisor = ActionOptionAdvisor(
            self.config.create_model(task, dict(os.environ), self.telemetry,
                                     temperature=self._generation_settings(game_id).temperature), self.telemetry,
            timeout_seconds=self.config.runtime.followup_timeout_seconds,
        )
        context = program.current_action_context(snapshot) if program and snapshot else {}
        recent = tuple(item.text for item in self.store.player_inputs_for(game_id)[-4:]
                       if not item.text.startswith("/")) if game_id else ()
        return await advisor.suggest(body, presentation_mode, game_id, scenario_id,
                                     story_context=context, recent_actions=recent)

    async def _freeform_novel(self, package: ScenarioPackage, game_id: str, text: str, turn_id: str,
                              segments: tuple[StorySegment, ...], progress: TurnProgress | None = None
                              ) -> tuple[str, tuple[StorySegment, ...]]:
        return await present_freeform_novel(
            self.store, package, self._novel_presenter(package, game_id),
            game_id, text, turn_id, segments, progress,
        )

    @staticmethod
    def _view(game_id: str, catalog_id: str, mode: str, body: str,
              snapshot, guidance, *, complete: bool = False,
              opening: str = "", turn_id: str | None = None,
              segments: tuple[StorySegment, ...] = (),
              program: CampaignProgram | None = None, gate_id: str | None = None,
              time_of_day: str = "", presentation_mode: str = "interactive",
              action_options: tuple[ActionOption, ...] = (),
              clock: StoryClock | None = None,
              status_fields: tuple[StatusField, ...] = (),
              time_unit: str = "tick") -> dict:
        campaign = snapshot.data.get("campaign")
        return {"game_id": game_id, "catalog_id": catalog_id, "mode": mode,
                "presentation_mode": presentation_mode,
                "opening": opening, "body": body,
                "segments": [part.to_dict() for part in segments],
                "interaction": campaign_interaction(program, snapshot, gate_id) if program else None,
                "suggestions": list(guidance.items),
                "action_options": [option.model_dump() for option in action_options],
                "tick": snapshot.tick, "state_version": snapshot.version,
                "day": (campaign.get("day") if isinstance(campaign, dict) else
                        snapshot.tick // clock.ticks_per_day + 1 if clock is not None else
                        snapshot.tick + 1 if time_unit == "day" else None),
                "time_of_day": time_of_day or (clock.period(snapshot.tick) if clock is not None else None),
                "status_fields": project_status_fields(status_fields, snapshot.data),
                "complete": complete, "turn_id": turn_id}

    async def _settle_status(self, package: ScenarioPackage, game_id: str, turn_id: str,
                             player_text: str,
                             observations: tuple[Observation, ...]):
        if not any(field.automatically_updated for field in package.status_fields):
            return self.store.load(game_id)
        model = self.config.create_model(
            "adjudication", dict(os.environ), self.telemetry,
            temperature=self._generation_settings(game_id).temperature,
        )
        proposer = ModelStatusAdjudicator(model, self.telemetry)
        try:
            return await settle_status(self.store, game_id, turn_id, player_text,
                                       package.status_fields, observations,
                                       proposer.propose)
        except Exception:
            logging.getLogger(__name__).exception("status review failed for game %s", game_id)
            return self.store.load(game_id)

    async def create_save(self, token: str, catalog_id: str,
                          play_mode: str | None = None) -> dict:
        player_id = self.accounts.resolve_token(token)
        item = self._listing_for(player_id, catalog_id)
        if item.retired:
            raise ValueError("this game is no longer available for new saves")
        selected_mode = play_mode or item.mode
        if selected_mode not in item.supported_play_modes:
            raise ValueError("this game does not support the selected play mode")
        self._require_model_key()
        package = self._package_for_mode(ScenarioPackage.load(item.package_path), selected_mode)
        game_id = uuid4().hex
        package.seed_game(self.store, game_id, include_campaign=selected_mode == "campaign")
        self.accounts.create_save(player_id, item.game_id, game_id,
                                  item.package_id, item.package_version, item.fingerprint,
                                  selected_mode)
        result = await self._open_save(item, package, game_id, opening=package.opening,
                                       play_mode=selected_mode)
        self.accounts.store_intro(game_id, result)
        return result

    async def resume_save(self, token: str, game_id: str) -> dict:
        player_id = self.accounts.resolve_token(token)
        async with self._player_lock(player_id):
            return await self._resume_save_for_player(player_id, game_id)

    async def _resume_save_for_player(self, player_id: str, game_id: str) -> dict:
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        latest = self.accounts.latest_turn_response(game_id)
        snapshot = self.store.load(game_id)
        if latest is None:
            intro = self.accounts.get_intro(game_id)
            if (intro is not None and snapshot.version == intro.get("state_version")
                    and not self.store.ready_work(game_id, snapshot.tick)
                    and ((record.play_mode or item.mode) != "campaign" or "interaction" in intro)):
                return {**intro, "opening": ""}
        if (latest is not None and snapshot.version == latest["state_version"]
                and not self.store.ready_work(game_id, snapshot.tick)
                and ((record.play_mode or item.mode) != "campaign" or "interaction" in latest)):
            return {**latest, "opening": ""}
        package = self._package_for_mode(ScenarioPackage.load(item.package_path),
                                         record.play_mode or item.mode)
        result = await self._open_save(item, package, game_id,
                                       opening=package.opening if latest is None else "",
                                       play_mode=record.play_mode or item.mode)
        if latest is None:
            self.accounts.store_intro(game_id, result)
        return result

    async def _open_save(self, item: GameListing, package: ScenarioPackage,
                         game_id: str, opening: str = "",
                         play_mode: str | None = None) -> dict:
        mode = play_mode or item.mode
        if mode == "campaign":
            program, session = self._campaign(item, package, game_id)
            authored = package.authored_prologue if package.presentation_mode == "novel" else ""
            outcome = await session.start(game_id, present_opening=False)
            opening_text = (authored or "\n\n".join(part for part in (opening, outcome.text)
                                                   if part.strip())
                            if package.presentation_mode == "novel" else opening)
            body = "" if package.presentation_mode == "novel" else outcome.text
            segments = (tuple(part for part in outcome.segments if part.kind == "prompt")
                        if package.presentation_mode == "novel" else outcome.segments)
            guidance = await GuidanceAdvisor(self.store, package, program,
                                             telemetry=self.telemetry,
                                             turns_per_story_tick=item.turns_per_story_tick).advise(
                game_id, outcome.snapshot, gate_id=outcome.gate_id,
                complete=outcome.complete, visible_text=opening_text or body)
            action_options: tuple[ActionOption, ...] = ()
            return self._view(game_id, item.game_id, mode, body,
                              outcome.snapshot, guidance, complete=outcome.complete,
                              opening=opening_text, segments=segments,
                              program=program, gate_id=outcome.gate_id,
                              time_of_day=outcome.time_of_day,
                              presentation_mode=package.presentation_mode,
                              action_options=action_options,
                              status_fields=package.status_fields, time_unit=package.time_unit)
        snapshot = self.store.load(game_id)
        opening_text = (package.authored_prologue or opening
                        if item.mode == "freeform" else opening)
        guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
            game_id, snapshot, visible_text=opening_text)
        # Creating a save should not wait for an optional model suggestion.
        action_options: tuple[ActionOption, ...] = ()
        clock = (StoryClock(package.ticks_per_day * item.turns_per_story_tick)
                 if package.ticks_per_day is not None else None)
        return self._view(game_id, item.game_id, mode, "", snapshot, guidance,
                          opening=opening_text, presentation_mode=package.presentation_mode,
                          action_options=action_options, clock=clock,
                          status_fields=package.status_fields, time_unit=package.time_unit)

    async def turn(self, token: str, game_id: str, text: str,
                   request_id: str | None = None, progress: TurnProgress | None = None) -> dict:
        player_id = self.accounts.resolve_token(token)
        async with self._player_lock(player_id):
            return await self._turn_for_player(player_id, game_id, text, request_id, progress)

    async def _turn_for_player(self, player_id: str, game_id: str, text: str,
                               request_id: str | None, progress: TurnProgress | None) -> dict:
        record = self.accounts.get_save(player_id, game_id)
        item = self._verified_listing(record)
        mode = record.play_mode or item.mode
        preview = self.moderation.preview_for(game_id, player_id) is not None
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
        if preview and self.moderation.preview_turn_count(game_id) >= 12:
            raise ValueError("review preview has reached its 12-turn limit")
        if self.billing is not None and not preview:
            self.billing.require_credit(player_id)
        package = self._package_for_mode(ScenarioPackage.load(item.package_path), mode)
        turn_id = f"portal-{request_id}"
        context = collect_usage() if self.billing is not None and not preview else nullcontext(None)
        preferences = () if preview else await self._preferences_for(player_id)
        with context as meter, player_preferences_scope(preferences):
            recovered = (await self._recover_freeform(item, package, game_id, text, turn_id)
                         if mode == "freeform" else None)
            if recovered is not None:
                view = recovered
            elif mode == "campaign":
                review_status = any(field.automatically_updated for field in package.status_fields)
                visible_before = ({item.observation_id
                                   for item in self.store.observations_for(game_id, "player")}
                                  if review_status else set())
                program, session = self._campaign(item, package, game_id)
                outcome = await session.submit(game_id, text, turn_id, progress=progress)
                visible_after = (tuple(
                    item for item in self.store.observations_for(game_id, "player")
                    if item.observation_id not in visible_before
                    or item.event_id.startswith(f"{turn_id}:")
                ) if review_status else ())
                await emit(progress, "preview", body=outcome.text,
                           segments=[part.to_dict() for part in outcome.segments])
                if review_status:
                    await emit(progress, "stage", stage="status")
                snapshot = await self._settle_status(package, game_id, turn_id, text,
                                                     visible_after)
                await emit(progress, "stage", stage="guidance")
                guidance = await GuidanceAdvisor(self.store, package, program,
                                                 telemetry=self.telemetry,
                                                 turns_per_story_tick=item.turns_per_story_tick).advise(
                    game_id, snapshot, gate_id=outcome.gate_id,
                    complete=outcome.complete, visible_text=outcome.text)
                action_options = await self._action_options(
                    outcome.text, package.presentation_mode,
                    game_id=game_id, scenario_id=package.package_id,
                    gate_id=outcome.gate_id, complete=outcome.complete,
                    program=program, snapshot=snapshot,
                )
                view = self._view(game_id, item.game_id, mode, outcome.text,
                                  snapshot, guidance, complete=outcome.complete,
                                  turn_id=turn_id, segments=outcome.segments,
                                  program=program, gate_id=outcome.gate_id,
                                  time_of_day=outcome.time_of_day,
                                  presentation_mode=package.presentation_mode,
                                  action_options=action_options,
                                  status_fields=package.status_fields, time_unit=package.time_unit)
            else:
                outcome = await self._react(item, package, game_id).run_turn(
                    game_id, text, turn_id, progress=progress,
                )
                body, segments = outcome.narration, outcome.segments
                if package.presentation_mode == "novel":
                    body, segments = await self._freeform_novel(
                        package, game_id, text, turn_id, segments, progress,
                    )
                await emit(progress, "preview", body=body,
                           segments=[part.to_dict() for part in segments])
                if any(field.automatically_updated for field in package.status_fields):
                    await emit(progress, "stage", stage="status")
                    await self._settle_status(package, game_id, turn_id, text,
                                              outcome.player_observations)
                await emit(progress, "stage", stage="guidance")
                guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
                    game_id, self.store.load(game_id), visible_text=body)
                action_options = await self._action_options(
                    body, package.presentation_mode, game_id=game_id,
                    scenario_id=package.package_id,
                )
                clock = (StoryClock(package.ticks_per_day * item.turns_per_story_tick)
                         if package.ticks_per_day is not None else None)
                view = self._view(game_id, item.game_id, mode, body,
                                  self.store.load(game_id), guidance, turn_id=turn_id,
                                  segments=segments,
                                  presentation_mode=package.presentation_mode,
                                  action_options=action_options, clock=clock,
                                  status_fields=package.status_fields, time_unit=package.time_unit)
        if self.billing is not None and not preview:
            with self.telemetry.span(
                "billing-settlement",
                {"game_id": game_id, "request_id": request_id,
                 "model_calls": len(meter.records),
                 "pricing_version": self.billing.policy.pricing_version},
                session_id=session_id_for_game(game_id, item.package_id),
            ) as span:
                billed = self.billing.settle_turn(player_id, game_id, request_id,
                                                  text, view, meter.records)
                span.metric("story.credits_charged", billed["billing"]["charged_milli_points"] / 1000)
                span.metric("story.input_tokens", float(billed["billing"]["input_tokens"]))
                span.metric("story.output_tokens", float(billed["billing"]["output_tokens"]))
                self._queue_memory_input(player_id, game_id, request_id, text)
                return billed
        self.accounts.store_turn_response(game_id, request_id, text, view)
        if not preview:
            self._queue_memory_input(player_id, game_id, request_id, text)
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
        await self._react(item, package, game_id).run_ready_work(game_id)
        snapshot = self.store.load(game_id)
        visible = [observation for observation in self.store.observations_for(game_id, "player")
                   if observation.event_id.startswith(f"{turn_id}:")]
        segments = tuple(segment_for_observation(self.store, game_id, item) for item in visible)
        body = "\n\n".join(item.body_text for item in segments) or "上次操作已提交，暂时没有新的可见变化。"
        if package.presentation_mode == "novel":
            body, segments = await self._freeform_novel(package, game_id, text, turn_id, segments)
            snapshot = self.store.load(game_id)
        await self._settle_status(package, game_id, turn_id, text, tuple(visible))
        snapshot = self.store.load(game_id)
        guidance = await GuidanceAdvisor(self.store, package, telemetry=self.telemetry).advise(
            game_id, snapshot, visible_text=body)
        action_options = await self._action_options(
            body, package.presentation_mode, game_id=game_id,
            scenario_id=package.package_id,
        )
        clock = (StoryClock(package.ticks_per_day * item.turns_per_story_tick)
                 if package.ticks_per_day is not None else None)
        return self._view(game_id, item.game_id, "freeform", body, snapshot, guidance,
                          turn_id=turn_id, segments=segments,
                          presentation_mode=package.presentation_mode,
                          action_options=action_options, clock=clock,
                          status_fields=package.status_fields, time_unit=package.time_unit)
