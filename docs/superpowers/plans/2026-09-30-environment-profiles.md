# Environment Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the same player portal and game harness in local SQLite and online PostgreSQL environments by changing configuration and deployment secrets.

**Architecture:** Keep the existing `GameStore` and `PlayerRepository` contracts. Add one SQLAlchemy implementation of each contract for both database dialects, with a shared connection factory and Alembic migrations. Select local or online settings at startup; local keeps the current CLI defaults, while online obtains PostgreSQL and model credentials from environment variables and validates network host settings.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, psycopg 3, FastAPI, SQLite, PostgreSQL.

## Global Constraints

- Scenario and agent code must remain independent of storage selection.
- No private scenario assets or secrets enter the public repository.
- Existing SQLite saves must remain readable after migration.
- User preference: implement a coherent version, then perform one meaningful verification pass.

---

### Task 1: Shared database and migration

**Files:** `src/story_harness/adapters/sql_database.py`, `alembic.ini`, `src/story_harness/migrations/env.py`, `src/story_harness/migrations/versions/0001_initial.py`, `pyproject.toml`

**Interfaces:** `open_database(url: str) -> Engine`; `upgrade_database(url: str) -> None`.

- [x] Define schema for game events, observations, pending work, accounts, auth sessions, saves, and portal turns; add stable ordering columns for observations and turn responses.
- [x] Write a baseline migration that creates missing tables and upgrades legacy SQLite data in place.
- [x] Add SQLAlchemy, Alembic, and optional PostgreSQL driver dependencies.

### Task 2: Dialect-neutral repositories

**Files:** `src/story_harness/adapters/sql_store.py`, `src/story_harness/portal/sql_repository.py`, `src/story_harness/adapters/store.py`, `src/story_harness/portal/repository.py`

**Interfaces:** `SQLGameStore(engine: Engine)`, `SQLPlayerRepository(engine: Engine)` implementing the existing protocols.

- [x] Implement atomic snapshot/event/work commits and optimistic game version checks with SQLAlchemy statements.
- [x] Implement accounts, hashed bearer sessions, save ownership, and idempotent turn responses with the same schema in both dialects.
- [x] Keep existing public SQLite class names as compatibility wrappers that use the shared implementation.

### Task 3: Local and online launch profiles

**Files:** `src/story_harness/adapters/runtime_config.py`, `src/story_harness/portal/service.py`, `src/story_harness/portal/http_api.py`, `src/story_harness/cli/portal_api.py`, `config/local.json`, `config/online.json`, `README.md`, `README.en.md`

**Interfaces:** `HarnessConfig.load(path)`, `HarnessConfig.create_database()`, CLI `--profile local|online`.

- [x] Route both profiles through the shared repositories and migrations.
- [x] Validate `DATABASE_URL`, model key, and allowed hosts at startup; keep secrets in environment variables.
- [x] Let online FastAPI run behind a reverse proxy with configured host and origin allowlists; preserve loopback-only local defaults.
- [x] Document exact local and online startup commands and migration behavior.

### Task 4: Final verification

**Files:** `tests/test_environment_profiles.py`

- [x] Verify local SQLite end to end, online configuration validation, migration of a legacy SQLite save, and repository parity on SQLite.
- [x] Run the full test suite after implementation; fix concrete failures and rerun affected tests. A temporary PostgreSQL container also verified the online API flow.
