# StoryLoop Harness

`storyloop-harness` is an interactive narrative library. It runs the default
single-call scene generator, validates proposed state changes and commits
causal events through an injected store. Python 3.12+ is required.

## Install and run offline

From this package directory:

```sh
python -m pip install .
python examples/offline_turn.py
```

The example uses the included freeform scenario, an in-memory store and a
schema-valid deterministic model. It prints the story and committed snapshot
version without credentials, HTTP, SQL, an account or a wallet.

```python
from storyloop_harness import ScenarioPackage, TurnEngine, TurnInput
from storyloop_harness.testing import InMemoryGameStore, OfflineModel

package = ScenarioPackage.load("examples/freeform")
store = InMemoryGameStore()
package.seed_game(store, "game")
engine = TurnEngine(store, package, OfflineModel())
outcome = await engine.run_turn(
    TurnInput("game", "Hello", "turn-1", package.version)
)
```

The top-level facade exports exactly `ScenarioPackage`, `TurnEngine`,
`TurnInput`, `TurnOutcome`, `GameStore`, `ModelPort`, and the optional `CampaignContext` protocol.
`TurnInput.scenario_version` must match both the engine's package and the saved
scenario. Authorization and request/account ownership belong to the caller.

`ModelPort` is an async callable accepting messages and `structured_model` and
returning an object with `metadata` containing the structured result.
`generation.CompatibleOpenAIChatModel` adapts AgentScope 2.0.9; credentials
and endpoint routing are supplied by the caller. The adapter reports usage
through `usage.record_model_usage`; custom adapters can call the same
hook. `TurnOutcome.model_usage` is scoped to the current call, and contains no
prices or settlement data. The deterministic offline model reports zero tokens.

`TurnOutcome.events` contains successful commits made by this invocation.
Replaying a saved turn returns the saved narrative and snapshot without another
model call; its event and usage tuples are empty when no further work commits.
Existing result fields, including player-visible observations, remain intact.
The `GameStore.commit` expected version protects state writes. The minimal
memory store enforces this check and applies each commit atomically, but is not
persistent and is intended for examples and adapter contract tests.

## Product integration

`TurnEngine` accepts `clock`, `program` (a `CampaignContext`), `max_responders`,
`context_window_tokens`, `max_steps`, `telemetry`, and `legacy_npc_reply`.
`run_turn(TurnInput, progress=..., max_tick=...)` supports progress callbacks and
campaign time boundaries. `proposed_options` and `proposed_status` read persisted
turn suggestions; `run_ready_work` drains previously queued work, including an
injected legacy NPC handler. Standalone background work reports usage to the
caller's `usage.collect_usage` scope; a normal turn returns it in `model_usage`.

Additional explicit public surfaces support product adapters:

- `advanced`: story events, snapshots, validation, projection, story clocks and
  work contracts used by persistence and legacy integrations. This larger
  compatibility surface is separate from the ordinary turn facade.
- `generation`: structured model transport, formatter and action suggestions.
- `telemetry`: tracing protocols and no-op span implementation.
- `usage`: token usage records and scoped collection, with no pricing policy.

Platform callers must settle using the returned turn usage. Product generation
outside the engine may use its own collection scope; merge those records with
`TurnOutcome.model_usage` exactly once. Nested scopes deliberately do not copy
records to outer collectors. Missing model usage raises before settlement.

## Development

```sh
python -m pip install '.[test]'
python -m pytest tests -q
```

Platform credentials, billing, SQL, service telemetry configuration and the
web application live in the separate `storyloop-platform` distribution.
The former `story_harness` import namespace has been removed.
