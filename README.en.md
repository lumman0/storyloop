# StoryLoop Platform

[中文](README.md) · [English](README.en.md)

StoryLoop Platform is a player and creator platform for AI interactive fiction, providing scenario management, single-player saves, accounts, credit settlement, and a web interface. It integrates narrative generation and event execution through the public APIs of the independent [StoryLoop Harness](https://github.com/storyloop0/storyloop-harness).

Ordinary turns use `single_call`: project the history and experiences visible to the player and relevant NPCs, assemble a scene context, generate one structured proposal with a shared scene model, then validate and commit events, state, and observations in the backend. Character contexts represent identity, experience, and information perspectives; individual NPCs do not run independent ReAct instances.

## Current capabilities

| Capability | Scope |
| --- | --- |
| Interactive fiction | Free text input, character replies, action suggestions, interactive and novel presentation; story milestones and elapsed story time. |
| Scenario content | Versioned packages, character cards, initial state, declared mutable fields, openings, and visibility-filtered JSON worldbooks. Public examples live in `examples/`. |
| Player experience | React and FastAPI; accounts, catalog, private scenario uploads, save creation and resume, history, and SSE turn progress and story segments. |
| Content management | Immutable author submissions, isolated reviewer previews, and administrator controls for accounts, roles, public versions, invitations, and audit records. |
| Storage and settlement | SQLAlchemy with local SQLite and online PostgreSQL; persisted events, observations, state, pending work, and accounting. Request IDs support turn retries and settlement recovery. |
| Optional integrations | OpenAI-compatible model APIs, Langfuse tracing, and player-approved Mem0 preference extraction. Player profiles remain separate from game facts and NPC experiences. |

## Architecture and boundaries

```text
React / Vite → FastAPI platform → StoryLoop Harness
                       ↓          projection → generation → validation → commit
                 SQL saves and accounting
```

The platform owns authentication, content lifecycle, model adapters, persistence, billing, and deployment; harness owns the reusable narrative execution contract. The dependency range is `storyloop-harness>=0.2,<0.3`, with source revision `cb2be84dad44cbfc6e18d16eebc071c2234f7b22` pinned in `pyproject.toml`. `scripts/build_harness.py` builds a wheel from that revision, and the installation below names that artifact explicitly.

The shared scene model sees multiple character contexts, so perspective projection and behavioral constraints do not provide hard information isolation between characters. Long-session context selects recent and relevant experiences from committed history while retaining original events; the current worldbook retrieves JSON entries. One ordinary scene generation does not imply that openings, suggestions, or every other feature use only one model call.

The project is under active incubation. APIs, configuration, and storage formats may change without backward compatibility guarantees. The only current turn engine is `single_call`; saves containing obsolete `npc_reply` pending work are rejected and should be recreated.

## Quick start

Use Python 3.12+, Node.js 24, and Git. Run the following PowerShell commands at the repository root using a dedicated virtual environment. Use an empty `dist/harness` directory for the first build.

```powershell
py -3.12 -m venv .venv
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe scripts/build_harness.py --out-dir dist/harness
.\.venv\Scripts\python.exe -m pip install dist/harness/storyloop_harness-0.2.0-py3-none-any.whl -e ".[agents,portal]"
.\.venv\Scripts\python.exe scripts/check_environment.py --config config/local.json
```

The environment check should point to this checkout's interpreter and source. It checks import locations and the configured storage driver, without testing database or model connectivity.

Live play requires a model key. Set it in the environment and start the local API:

```powershell
$env:STORY_BAILIAN_API_KEY = "your-api-key"
.\.venv\Scripts\python.exe -m storyloop_platform.cli.portal_api --catalog config/games.example.json --config config/local.json --db game.sqlite3
```

Alternatively, copy `config/application.local.example.json` to the Git-ignored `config/application.local.json` and fill in `models.api_key`. `config/local.json` resolves this file relative to its own directory; a nonempty `STORY_BAILIAN_API_KEY` takes precedence. The current local configuration selects Bailian's Hong Kong OpenAI-compatible endpoint and `deepseek-v4.1-flash`; adjust the endpoint, task models, and billing settings for another service. On Windows, the local CLI can prompt for a missing key and save it with DPAPI protection.

Start the frontend in another terminal:

```powershell
cd web
npm ci
npm run dev
```

Open the [local frontend](http://127.0.0.1:5173) to register, create a save, and play. Vite proxies `/v1` to `127.0.0.1:8765`; API documentation is available at [local API /docs](http://127.0.0.1:8765/docs). Local mode uses SQLite and disables player profiles by default.

On macOS/Linux, create the environment with `python3.12 -m venv .venv` and replace Python paths with `.venv/bin/python`. Use `export STORY_BAILIAN_API_KEY="your-api-key"` for the key and `unset PYTHONPATH` to clear import overrides. Other CLI arguments and npm commands are the same.

## Development and verification

Install the test integrations and the uv version used by CI, then run the backend regressions with offline model fixtures. The wheel installation test invokes `uv`, builds the pinned harness revision, and creates a temporary environment, so a first run may still need network access to download dependencies.

```powershell
.\.venv\Scripts\python.exe -m pip install uv==0.11.25 dist/harness/storyloop_harness-0.2.0-py3-none-any.whl -e ".[agents,portal,observability,player-memory,online,test]"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
$env:STORY_BAILIAN_API_KEY = "offline-test"
$env:LANGFUSE_PUBLIC_KEY = ""
$env:LANGFUSE_SECRET_KEY = ""
.\.venv\Scripts\python.exe -m pytest tests -q
cd web
npm ci
npm test
npm run build
```

For browser regressions, also run `npx playwright install chromium` and `npm run test:e2e`; these use a mock API. CI checks the backend with Python 3.12 on Windows/Linux and the frontend and browser flows with Node.js 24 on Linux. The `offline-test` value is not a live model credential.

```text
src/storyloop_platform/  API, SQL, configuration, model adapters, billing, CLI
web/                    React / Vite frontend
config/                 Runtime configuration and catalog examples
examples/               Synthetic scenario packages
tests/                  Backend and independent installation regressions
deploy/ecs/             Docker Compose deployment resources
```

## Limitations and future directions

Offline functional tests do not establish live narrative quality, the effectiveness of character information constraints, or production recovery guarantees. Live models, PostgreSQL, and deployment environments require separate validation. A single API worker is currently recommended; settlement snapshots support completed-turn recovery, but there is no complete journal of individual model calls or guaranteed recovery across processes or multiple workers. Context selection is also constrained by the available window budget.

Future work may explore context provenance, selection reasons and budget reports, long-session memory strategies, narrative quality and cost comparisons, and additional failure recovery cases. These are future directions, not claims of implemented capabilities.

## License

This project uses the [MIT License](LICENSE). StoryLoop Harness also uses MIT.
