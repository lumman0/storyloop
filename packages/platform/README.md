# StoryLoop Platform

`storyloop-platform` 0.1.0 is the player and creator product built on
`storyloop-harness`. Its declared dependency is exactly the compatibility range
`storyloop-harness>=0.1,<0.2`; the current lock and CI artifact pin resolve to
**0.1.0**. It imports `storyloop_harness` public surfaces only.

## Install and run

Python 3.12+ is required; frontend verification uses Node.js 24. From the repository
root, for editable development:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install -e packages/harness -e 'packages/platform[agents,portal]'
python -m storyloop_platform.cli.portal_api --catalog config/games.example.json --config config/local.json --db game.sqlite3
```

For artifact installation, build both wheels with `uv build --no-sources --wheel
packages/harness --out-dir dist` and the equivalent command for `packages/platform`.
Then install the pinned local harness and platform with their dependencies:

```sh
python -m pip install --find-links dist 'storyloop-harness==0.1.0' 'storyloop-platform[agents,portal]==0.1.0'
cd packages/platform/web
npm ci
npm run dev
```

The frontend uses `http://127.0.0.1:5173` and proxies `/v1` to the API on port 8765.
Supply a real `STORY_BAILIAN_API_KEY` for interactive model generation. Config
examples live in `config/`; bundled local/online defaults ship in the wheel.
Local mode uses SQLite; online mode requires configured PostgreSQL. Optional
`observability`, `player-memory`, and `online` extras supply service integrations.
Private content and credentials remain outside Git. See [setup](../../README.en.md),
[deployment](../../docs/deployment.md), and [verification](../../docs/verification.md).

## Ownership and recovery

The platform owns HTTP/SSE, authentication, cookies, accounts, save ownership,
content upload/versioning/moderation, SQL repositories and migrations, prices,
wallet settlement, request receipts, deployment, and frontend presentation.
It injects storage, model and telemetry ports into harness `TurnEngine` and
settles `TurnOutcome.model_usage` exactly once. Mem0 player preferences and
Langfuse service configuration also belong here.

Only `single_call` is accepted by runtime configuration. A platform legacy adapter
handles persisted `npc_reply` work; the historical multi-agent beta is archived,
not a current route. See [architecture](../../docs/architecture.md).

A full-turn settlement snapshot and idempotent receipt recover the window after
successful generation. Earlier failures without complete usage evidence may
require manual recovery; there is no per-model-call journal or multi-instance
execution guarantee. See [turn recovery](../../docs/turn-recovery.md).

## Versioning and a later repository split

Local development may use workspace/editable sources. CI consumes the harness
wheel from a separate successful job, pinned to 0.1.0, then independently builds
and installs platform before integration tests. Future separate repositories
will publish harness first, update the platform dependency source/version, and
change Git remotes; public imports and runtime behavior must remain the same.
Organization creation, remote migration and package publication are a later plan.
