# Harness Package Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the default StoryLoop narrative runtime an independently installable `storyloop-harness` Python package while the player product becomes a separate `storyloop-platform` package in the same repository.

**Architecture:** First remove the default engine's imports of beta Agent classes and SQL implementations. Then relocate the narrative domain and default engine into a package with explicit public ports, and rewire the platform as its consumer. Keep a compatibility layer only while existing tests and old persisted work are migrated. GitHub repository separation is a later plan after both packages build independently.

**Tech Stack:** Python 3.12, Pydantic 2, AgentScope 2.0.9, SQLAlchemy 2, FastAPI, uv, pytest, React/Vite.

## Global Constraints

- `storyloop-harness` / `storyloop_harness` is an interactive narrative runtime, not a generic Agent framework; `single_call` is its first supported engine.
- `storyloop-platform` / `storyloop_platform` owns React, FastAPI, auth, catalog/upload/moderation, SQL persistence, wallet/settlement, Mem0 configuration and deployment.
- The dependency direction is `platform → harness`; harness cannot import platform, and platform must use harness public modules.
- New configuration accepts only `single_call`. Preserve a recoverable path for persisted `npc_reply` work before removing beta implementation.
- World facts and wallet accounting retain their existing authority and failure semantics. No performance baseline, microservices, queue, or new multi Agent feature is part of this plan.
- Existing AgentScope upgrade changes are uncommitted at plan creation. Isolate them from package migration commits.

---

## File map

| Destination | Responsibility | Current source |
| --- | --- | --- |
| `packages/harness/src/storyloop_harness/contracts.py` | `MainDecision`, `TurnOutcome`, `TurnInput`, story event and usage value types | `agents/main_agent.py`, `runtime/game_session.py`, `core/contracts.py`, `core/billing.py` |
| `packages/harness/src/storyloop_harness/ports.py` | `GameStore`, `ModelPort`, `Telemetry` contracts | `adapters/store.py`, model call sites, `adapters/telemetry.py` |
| `packages/harness/src/storyloop_harness/core/` | World events, state, actions, perception, open effects | `src/story_harness/core/` except pricing policy |
| `packages/harness/src/storyloop_harness/world/` | Package parsing, story blueprint and visibility rules | `src/story_harness/world/` |
| `packages/harness/src/storyloop_harness/runtime/` | `single_call`, queue, context projection, scene generation and story clock | relevant `runtime/` and `agents/` modules |
| `packages/harness/src/storyloop_harness/models/` | AgentScope message/formatter/model adapter without environment routing | `adapters/agentscope_message.py`, `agents/openai_formatter.py`, model portion of `adapters/model_config.py` |
| `packages/harness/src/storyloop_harness/testing/` | Minimal in-memory `GameStore` and offline model for public example | extract from tests/CLI demo |
| `packages/platform/src/storyloop_platform/` | Portal, SQL adapters, config/model routing, billing and CLI | current `portal/`, SQL adapters, runtime config and CLI |
| `packages/platform/web/`, `packages/platform/deploy/` | Product UI and deployment | current `web/`, `deploy/` |

The physical move should preserve focused files under these directories. Do not combine all of `runtime/` or `agents/` into a single file. Beta only files (`main_agent.py`, `npc_agent.py`, `quiet_agent.py`, `react_factory.py`, `game_session.py`, selector and related beta tests) are archived after their shared types have been separated. If persisted `npc_reply` work exists, a narrowly scoped compatibility handler remains in platform until those items are processed; it is not a selectable turn engine.

### Task 1: Stabilize and archive the existing SDK migration

**Files:** `pyproject.toml`, `uv.lock`, current modified `src/story_harness/` and `tests/` files; Git tag and branch metadata.

**Interfaces:** Produces a reviewed commit containing AgentScope 2.0.9 migration, and an immutable beta archive reference. Later tasks start from this exact commit.

- [ ] **Step 1: Inspect the exact change set.** Run `git status --short` and `git diff --check`. Verify the only new design/plan commit is already separate and review the SDK diff before staging.
- [ ] **Step 2: Run the existing suite.** Run `.\.venv\Scripts\python.exe -m pytest tests -q --tb=short --disable-warnings` and `$env:UV_CACHE_DIR='D:\ai\.uv-cache'; uv lock --check --offline`. Expected: all backend tests pass and lock check exits 0.
- [ ] **Step 3: Commit only SDK migration files.** Stage `pyproject.toml`, `uv.lock`, affected runtime/model files and their tests by explicit path; inspect `git diff --cached --name-only`; commit `chore: upgrade AgentScope runtime to 2.0.9`. Never use `git add -A` while unrelated work exists.
- [ ] **Step 4: Preserve beta source.** Create a non-moving tag `multi-agent-beta-archive-2026-10` at the verified SDK commit and an `archive/multi-agent-beta-2026-10` branch pointing to the same commit. Do not push until remote migration work is separately approved and ready.

### Task 2: Separate default engine contracts from beta and SQL

**Files:** Create `src/story_harness/core/decisions.py`, `src/story_harness/core/turn_result.py`, `src/story_harness/core/store_port.py`; modify `agents/main_agent.py`, `agents/scene_turn.py`, `runtime/single_call.py`, `runtime/game_session.py`, `runtime/runner.py`, `runtime/schedule.py`, `world/scenario.py`, `adapters/store.py`; test `tests/test_engine_contract.py`, `tests/test_single_call.py`.

**Interfaces:** Produces `MainDecision`, `TurnOutcome`, and `GameStore` at beta-free and SQL-free locations. The old import paths temporarily re-export the identical class objects for existing callers.

- [ ] **Step 1: Add red contract tests.** Assert `story_harness.core.decisions.MainDecision is story_harness.agents.main_agent.MainDecision`, `story_harness.core.turn_result.TurnOutcome is story_harness.runtime.game_session.TurnOutcome`, and `story_harness.core.store_port.GameStore is story_harness.adapters.store.GameStore`. Run `pytest tests/test_engine_contract.py -q`; expected import failures.
- [ ] **Step 2: Move definitions and update imports.** Keep the exact Pydantic fields of `MainDecision` from `main_agent.py`, the exact dataclass fields of `TurnOutcome` from `game_session.py`, and the exact method signatures of `GameStore` from `adapters/store.py`. In the old files use imports such as `from story_harness.core.decisions import MainDecision` instead of duplicate definitions. `SQLiteGameStore` remains in `adapters/store.py` for this task. Update `single_call.py` and `scene_turn.py` to import the new contracts directly. Move `StorySegment` beside `TurnOutcome` so the shared result no longer imports a beta module.
- [ ] **Step 3: Remove beta-only token estimator dependency.** Move `estimate_tokens` from `runtime/agent_context.py` to `core/token_budget.py`; have both old module and `scene_turn.py` import the same function. Add a test asserting the estimator returns the same value for Chinese and ASCII samples through both paths.
- [ ] **Step 4: Verify.** Run `pytest tests/test_engine_contract.py tests/test_single_call.py tests/test_scene_responder_context.py -q` and `git diff --check`; expected all pass. Commit `refactor: separate story turn contracts from beta agents`.

### Task 3: Stop new beta execution and preserve old work recovery

**Files:** Modify `src/story_harness/adapters/runtime_config.py`, `src/story_harness/portal/service.py`, `README.md`, `README.en.md`, `docs/architecture.md`; test `tests/test_runtime_config.py`, `tests/test_react_session.py`, `tests/test_turn_settlement_recovery.py`.

**Interfaces:** `HarnessConfig.load` rejects any `runtime.turn_engine` other than `single_call`. Platform creates only `SingleCallGameSession`. Persisted `npc_reply` work remains handled by the existing `legacy_npc_reply` adapter until a separate data migration removes it.

- [ ] **Step 1: Add red tests.** Test that an explicit `multi_agent_beta` config raises `ValueError` naming `runtime.turn_engine`; test that a normal `single_call` config loads; retain a test with an old `npc_reply` work item asserting it is processed once and not silently dropped.
- [ ] **Step 2: Restrict config and simplify assembly.** Change the validation branch to `if runtime_settings.turn_engine != "single_call": raise ValueError("runtime.turn_engine must be single_call")`. In `PlayerPortal._react`, remove the `make_react_session` branch and create `SingleCallGameSession` unconditionally, retaining the existing conditional `legacy_reply` construction for old pending work. Remove active imports of `react_factory` from portal. Isolate this old-work adapter as platform compatibility code; it does not become part of the public harness package.
- [ ] **Step 3: Update product documentation.** Describe `single_call` as the only current engine and identify the beta Git tag as historical. Remove instructions inviting users to select `multi_agent_beta`.
- [ ] **Step 4: Verify.** Run `pytest tests/test_runtime_config.py tests/test_single_call.py tests/test_turn_settlement_recovery.py -q`; then run full backend suite because service assembly changed. Commit `refactor: retire beta engine selection`.

### Task 4: Build an installable narrative harness without platform imports

**Files:** Create `packages/harness/pyproject.toml`, `packages/harness/src/storyloop_harness/__init__.py`, `contracts.py`, `ports.py`, focused `core/`, `world/`, `runtime/`, `models/`, `testing/` modules, `packages/harness/examples/offline_turn.py`, `packages/harness/tests/test_public_api.py`, `packages/harness/tests/test_import_boundary.py`; move relevant files from `src/story_harness/` after Tasks 2–3.

**Interfaces:** `from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput, TurnOutcome, GameStore, ModelPort` succeeds when only the harness wheel and its declared dependencies are installed. `TurnEngine.run_turn` is async and returns `TurnOutcome`; the initial implementation wraps the existing `SingleCallGameSession` behavior. `GameStore` has the exact methods required by that session. `ModelPort` supplies structured output generation used by `SingleSceneGenerator`.

- [ ] **Step 1: Add red package tests.** In `test_public_api.py`, import the six symbols above, load `examples/freeform`, run one offline turn with an in-memory store and fake model, and assert nonempty prose plus a committed snapshot version. In `test_import_boundary.py`, parse all harness Python files with `ast` and reject imports starting with `storyloop_platform` or `story_harness.portal`; reject imports of SQL modules from harness runtime files.
- [ ] **Step 2: Create package metadata and public facade.** Set `[project] name = "storyloop-harness"`, `requires-python = ">=3.12"`, and declare Pydantic 2 plus AgentScope `==2.0.9`, which the default generation path imports. Keep FastAPI, SQLAlchemy, Mem0 and Langfuse out of harness requirements. Export only the six public symbols in `__init__.py`; keep beta types out of the facade.
- [ ] **Step 3: Move the domain and default engine in focused batches.** Move `core/` and `world/` first; then `runner.py`, `schedule.py`, `story_clock.py`, `player_knowledge.py`, `player_input.py`, `turn_progress.py`, `presentation.py`, `single_call.py`, `scene_turn.py`, `action_advisor.py`, the message/formatter adapter, and the model adapter. Rewrite internal imports to `storyloop_harness.*`. Move `ModelUsage` as a value type into harness; have the model adapter report it through a harness usage hook collected into `TurnOutcome`. Leave `BillingPolicy`, pricing and wallet settlement in platform. Split model endpoint credentials/routing into platform; harness retains only the model adapter/port. Split telemetry protocol/no-op implementation into harness and Langfuse configuration into platform.
- [ ] **Step 4: Supply a real minimal example.** The in-memory store must implement the `GameStore` protocol's methods needed by one ordinary turn and commit with expected-version checking. The offline model returns a schema-valid deterministic scene. The example prints the generated prose and resulting snapshot version without account, SQL, HTTP or model credentials.
- [ ] **Step 5: Verify wheel independence.** Build the harness wheel, install it into a fresh temporary venv outside the repository root, clear `PYTHONPATH`, run its offline example, and run `packages/harness/tests`. Expected: no import of `story_harness`, `storyloop_platform`, FastAPI, SQL implementation or portal modules. Commit `feat: package independent storyloop narrative harness`.

### Task 5: Move platform-owned backend modules behind a new package name

**Files:** Create `packages/platform/pyproject.toml`, `packages/platform/src/storyloop_platform/__init__.py`, `portal/`, `adapters/`, `generators/`, `runtime/`, `legacy/`; move current `src/story_harness/portal/`, SQL adapters/migrations, runtime config/model routing, product-only generators and campaign/guidance/presentation helpers. Leave `web/`, `deploy/` and CLI locations unchanged for this task. Add `tests/test_platform_package_boundary.py`.

**Interfaces:** `storyloop_platform.portal.service.PlayerPortal` is the canonical product class. Existing `story_harness.portal.*` imports temporarily re-export identical objects so prior tests remain valid. Product modules may use harness public exports; remaining internal harness imports are inventoried for Task 6, not silently ignored. Platform has no reverse import from harness.

- [ ] **Step 1: Add red identity and ownership tests.** Assert the canonical `storyloop_platform.portal.service.PlayerPortal` import exists, old `story_harness.portal.service.PlayerPortal` is the same object, and `storyloop_harness` source contains no `storyloop_platform` import. Run `pytest tests/test_platform_package_boundary.py -q`; expected missing-module failure.
- [ ] **Step 2: Move platform-only modules.** Use `git mv` for portal, SQL/database/migration adapters, configuration/router modules and product-only generation/runtime helpers. Rewrite their intra-platform imports to `storyloop_platform.*`; leave thin old-path re-export modules under `src/story_harness/` for this stage. Keep `ScenarioPackage`, narrative contracts, default engine and ports in harness. Put the persisted `npc_reply` compatibility handler in `storyloop_platform.legacy` and keep its once-only regression green.
- [ ] **Step 3: Add package metadata.** Declare `[project] name = "storyloop-platform"`, Python `>=3.12`, and `storyloop-harness>=0.1,<0.2` as a required dependency. Resolve that dependency to `../harness` only in local uv workspace configuration; built wheel metadata must contain the version requirement, not an absolute filesystem path. Put SQLAlchemy, FastAPI, Mem0 and Langfuse only in platform or its extras. Build a platform wheel and import `storyloop_platform` in a clean environment; full portal execution becomes Task 6.
- [ ] **Step 4: Verify.** Run the identity/ownership test, legacy `npc_reply` recovery test, package build and full backend suite. Commit `refactor: relocate platform backend modules`.

### Task 6: Make the platform invoke only harness public APIs

**Files:** Modify `packages/platform/src/storyloop_platform/portal/service.py`, product model/router adapter, SQL store adapter, `packages/harness/src/storyloop_harness/__init__.py`, `ports.py`, `runtime/engine.py`, `packages/harness/tests/test_public_api.py`; add `tests/test_platform_harness_integration.py` and a static import-boundary test.

**Interfaces:** `PlayerPortal` constructs `storyloop_harness.TurnEngine` with a `GameStore` and `ModelPort`, calls `run_turn(TurnInput)` and consumes `TurnOutcome`. Extend the facade constructor to accept the existing projector/session settings (`clock`, campaign `program`, `max_responders`, `context_window_tokens`, `max_steps`, `telemetry`, `legacy_npc_reply`) so platform configuration remains effective. Platform settlement consumes `TurnOutcome.model_usage` and rejects missing usage as before. Public harness exports contain every type/function the platform legitimately needs; platform code does not import `storyloop_harness.core`, `.runtime`, `.world`, `.agents` or `.models` internals. SQL adapter implements `GameStore` and preserves expected-version commits. Legacy `npc_reply` handling stays platform-local.

- [ ] **Step 1: Add red platform integration tests.** Run one player action through `PlayerPortal` with an offline model and SQL-backed store. Assert visible prose, committed world event, one wallet settlement and idempotent replay of the same request ID. Add an AST test rejecting platform imports of harness private modules; run both tests to observe current failure.
- [ ] **Step 2: Route through the facade.** Replace direct construction of `SingleCallGameSession`, `SceneContextProjector` and `SingleSceneGenerator` in the service with `TurnEngine`/`TurnInput`. Forward every existing setting listed in the interface above, including campaign context and old `npc_reply` work handler. Read billed usage from the returned `TurnOutcome.model_usage`, not an outer nested collector. Add deliberate facade exports with focused public API tests for any legitimately shared story types. Do not export portal, SQL or wallet types from harness. The platform remains responsible for request deduplication, settlement snapshot and HTTP/SSE mapping.
- [ ] **Step 3: Preserve transaction/failure behavior.** Verify model failure leaves snapshot and wallet unchanged; committed result with lost response is recovered by the same request ID; old `npc_reply` work is still drained once. Use existing settlement tests plus the new integration test rather than duplicating their assertions in mocks.
- [ ] **Step 4: Verify.** Run harness API tests, platform import-boundary/integration tests, settlement recovery tests and full backend suite. Commit `refactor: route platform turns through harness API`.

### Task 7: Finish independent platform installation and migrate entry points

**Files:** Move `src/story_harness/cli/` to `packages/platform/src/storyloop_platform/cli/`; move `web/` and `deploy/` into `packages/platform/`; modify `alembic.ini`, migration package paths, Docker/Compose files, scripts and Python package data; update all tests still importing `story_harness.*`; remove old compatibility modules when no imports remain.

**Interfaces:** A platform wheel installed with a versioned harness wheel in a clean venv can import `storyloop_platform`, create the API and execute a player turn with no `story_harness` distribution or repository-root `PYTHONPATH`. Frontend build and deployment use the relocated paths. Archived beta CLI entry points do not appear as current product commands.

- [ ] **Step 1: Add red fresh-install smoke test.** Build both wheels, install them into a fresh venv outside the repository, clear `PYTHONPATH`, assert `find_spec("story_harness") is None`, import platform API, and execute an offline player turn. Capture the missing-package/import failure before path migration.
- [ ] **Step 2: Move CLI/UI/deploy paths and update imports.** Rewrite script entry commands, Alembic imports, Docker build contexts, Vite paths and package-data declarations. Replace remaining test imports with `storyloop_harness` or `storyloop_platform` ownership. Delete old compatibility shims only after an `rg` search shows no runtime/test import references.
- [ ] **Step 3: Verify.** Run fresh-install smoke, backend suite, frontend unit tests, `npm run build`, and existing browser interaction tests. Commit `refactor: complete independent platform package`.

### Task 8: Enforce the boundary and document independent use

**Files:** Modify CI workflow files under `.github/workflows/`, `README.md`, `README.en.md`, `docs/architecture.md`, `docs/verification.md`; update `packages/harness/README.md`, add `packages/platform/README.md`; test the package import checks from Tasks 4–7.

**Interfaces:** CI builds and tests each package separately, then installs a pinned harness artifact into platform integration tests. A future repository split requires only changing dependency source and Git remotes, not module imports or runtime behavior.

- [ ] **Step 1: Add CI gates.** Make harness tests, wheel build, import-boundary check, and offline example one job. Make platform installation, backend integration, frontend tests/build, and existing browser checks another job that depends on the harness build.
- [ ] **Step 2: Document public API and ownership.** Harness README includes install command, offline example, supported `single_call` semantics, storage/model ports and extension limits. Platform README includes setup, config, auth/content/wallet responsibilities and the exact harness version dependency. Architecture diagram shows platform depending on harness in one direction.
- [ ] **Step 3: Final verification.** Run `git diff --check`, both package builds, fresh-environment import tests, backend suite, frontend tests/build and applicable browser tests. Record precise passing counts and any external-model limitation in the completion report. Commit `docs: describe independent harness and platform packages`.

## Plan self-review

- Spec coverage: public narrative library, platform ownership, single-call default, beta freeze/legacy work, package install, one-way dependency, recovery semantics and later repository split gate all map to Tasks 1–8.
- The GitHub organization and physical repository split remain a second implementation plan, written only after the two package builds and platform integration pass; this avoids guessing organization availability and migration state.
- Preserve the persisted fields of `Snapshot`, `WorldEvent`, `Observation`, `PendingWork` and existing SQL rows exactly. New public wrappers can compose those values without rewriting saved data.
