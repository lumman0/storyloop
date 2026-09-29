# NPC World Agent Harness

[中文](README.md) · [English](README.en.md)

An AI interactive fiction harness. The director and each NPC use separate AgentScope ReAct contexts. Committed events define world state, and each character receives only observations available to them. The project provides a command-line player portal and FastAPI API, with no web frontend.

## Features

- Scenario packages with character cards, a visibility-scoped JSON worldbook, initial state, and scripted actions.
- A turn loop for player input, director decisions, NPC replies, world events, scheduled story beats, and branching endings. Each turn also offers separate next-step guidance.
- Registration, login, game selection, saves, and resume. The same storage interfaces support local SQLite and online PostgreSQL.
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

To play the public harbor scenario with a live model, start the player portal:

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_play --catalog config\games.example.json --db game.sqlite3
```

On first launch, register or log in. The portal asks for the model API key without echoing it when you start a game. Local mode uses [`config/local.json`](config/local.json) by default; pass `--config` to use another configuration. On Windows, it keeps the catalog settings, key, and valid login locally. Later, start it with:

```cmd
.\.venv\Scripts\python.exe -m story_harness.cli.portal_play
```

For an HTTP API, run `.\.venv\Scripts\python.exe -m story_harness.cli.portal_api --catalog config\games.example.json --db game.sqlite3`, then open `http://127.0.0.1:8765/docs`. For Langfuse, install `.[agents,portal,observability]` and set its environment variables.

On macOS/Linux, create the environment with `python3.12`, replace the Python path above with `.venv/bin/python`, and use `/` in scenario paths.

For online deployment, install `.[agents,portal,online]` and launch the same API with `--profile online`. See the [deployment guide](docs/deployment.md). Alembic migrates existing SQLite saves on first local startup.
