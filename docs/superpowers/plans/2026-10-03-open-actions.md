# Open Player Actions Implementation Plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

**Goal:** Let players attempt any contextual action while keeping durable world changes validated and visible to the right characters.

**Architecture:** Preserve declared action rules for special scripted transitions. Route other physical actions through a structured resolver that produces a committed event, a player-visible outcome, nearby witnesses, and targeted NPC follow-up. Validate all proposed state effects against explicitly declared mutable fields rather than a verb list. An internal resolution failure commits nothing and cannot advance the clock or settle billing.

**Tech Stack:** Python 3.12, AgentScope, Pydantic, SQLGameStore, pytest/unittest.

## Tasks

1. Add a scenario-level mutable field schema and strict effect validator. Keep the existing `actions` format compatible.
2. Add a structured freeform action resolver using the configured adjudication model and a narrow, player-safe context.
3. Wire freeform action events into `GameSession`: commit outcomes and validated effects, give nearby actors scoped observations, schedule only relevant NPC replies, and surface resolution prose directly.
4. Ensure an action with no declared rule no longer becomes a technical rejection; errors before commit leave time and billing unchanged. Mark action targets met without automatically increasing affinity.
5. Cover the empty-rule NPC action, validated object state change, and precommit failure with a small regression set. Run the relevant suite and one full suite pass.
