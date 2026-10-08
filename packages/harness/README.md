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
`TurnInput`, `TurnOutcome`, `GameStore`, and `ModelPort`.
`TurnInput.scenario_version` must match both the engine's package and the saved
scenario. Authorization and request/account ownership belong to the caller.

`ModelPort` is an async callable accepting messages and `structured_model` and
returning an object with `metadata` containing the structured result.
`models.agentscope.CompatibleOpenAIChatModel` adapts AgentScope 2.0.9; credentials
and endpoint routing are supplied by the caller. The adapter reports usage
through `models.usage.record_model_usage`; custom adapters can call the same
hook. `TurnOutcome.model_usage` is scoped to the current call, and contains no
prices or settlement data. The deterministic offline model reports zero tokens.

`TurnOutcome.events` contains successful commits made by this invocation.
Replaying a saved turn returns the saved narrative and snapshot without another
model call; its event and usage tuples are empty when no further work commits.
Existing result fields, including player-visible observations, remain intact.
The `GameStore.commit` expected version protects state writes. The minimal
memory store enforces this check and applies each commit atomically, but is not
persistent and is intended for examples and adapter contract tests.

## Development

```sh
python -m pip install '.[test]'
python -m pytest tests -q
```

The containing platform repository temporarily provides compatibility aliases
for existing `story_harness` imports. The harness package never imports those
aliases. Platform credentials, billing, SQL, service telemetry configuration and
web application code are outside this distribution.
