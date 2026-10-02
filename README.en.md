# NPC World Agent Harness

[中文](README.md) · [English](README.en.md)

An AI interactive fiction harness with a browser player portal. The director and each NPC use separate AgentScope ReAct contexts. Committed events define world state, and each character receives only observations available to them. The React frontend in `web/` talks to the FastAPI service.

## Features

- Scenario packages with character cards, a visibility-scoped JSON worldbook, initial state, and scripted actions.
- A turn loop for player input, director decisions, NPC replies, world events, scheduled story beats, and branching endings. Each turn also offers separate next-step guidance.
- Registration, login, game selection, saves, and resume. The same storage interfaces support local SQLite and online PostgreSQL.
- A browser catalog, personal saves, recoverable turn history, and separate next-step guidance.
- Immediate player-action echo, with SSE updates for live stages and committed visible story segments.
- Optional Langfuse traces, sessions, and metrics. Model routes and turn budgets are configurable.

`examples/freeform` and `examples/scheduled` are public synthetic scenarios. Private scenario sources and model keys are not included in this repository.

## Quick start

Use Python 3.12 or newer. From the repository root, run these commands in Windows CMD or PowerShell:

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[agents,portal]"
```

Run the offline example first; it does not need a model API key:

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.interaction_demo examples\freeform
```

To play with a live model, create a local credentials file:

```cmd
copy config\application.local.example.json config\application.local.json
```

Edit `models.api_key` in that file and paste your Bailian key. Git ignores the file. Local startup reads it automatically; `STORY_BAILIAN_API_KEY`, when set, takes precedence. Then start the API:

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --catalog config\games.example.json --config config\local.json --db game.sqlite3
```

In another terminal, start the separate frontend:

```cmd
cd web
npm install
npm run dev
```

Open `http://127.0.0.1:5173` to register, create a save, and play. Node.js 20.19+ is required. Vite proxies local `/v1` calls to the API at `127.0.0.1:8765`. The command-line `portal_play` remains available and can securely prompt for and retain the model key on Windows. API docs are at `http://127.0.0.1:8765/docs`. For Langfuse, install `.[agents,portal,observability]` and set its environment variables.

Catalog entries may set `turns_per_story_tick` (default `1`) for campaign games, so several ordinary interactions advance one scheduled story tick. `/next` still advances to the next story tick. This setting does not change a scenario package or save fingerprint.

On macOS/Linux, create the environment with `python3.12`, replace the Python path above with `.venv/bin/python`, and use `/` in scenario paths.

For online deployment, install `.[agents,portal,online]` and launch the same API with `--profile online`. See the [deployment guide](docs/deployment.md). Alembic migrates existing SQLite saves on first local startup.
