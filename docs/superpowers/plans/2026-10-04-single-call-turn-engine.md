# Single-call turn engine implementation plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

> **For agentic workers:** Execute this plan inline in the existing isolated worktree. Keep the legacy multi-agent engine selectable for beta use; the web profile uses the single-call engine.

**Goal:** Complete an ordinary player turn with one structured model request while preserving a separate committed history for every NPC.

**Architecture:** A deterministic context assembler reads the player's and relevant NPCs' recipient-scoped event histories. One scene model proposes the turn decision, prose, NPC speech, status deltas, and follow-up options. The runtime validates and commits events; scripted gates and time commands use authored data and need no model request. The existing ReAct engine remains behind a beta configuration switch.

**Tech Stack:** Python, AgentScope OpenAI-compatible model adapter, Pydantic, SQL GameStore, FastAPI SSE, SQLite/PostgreSQL.

## Global constraints

- Production web uses `single_call`; beta multi-agent is not exposed as a player choice.
- One successful ordinary web turn invokes the scene model exactly once. Backend retries at the HTTP transport layer remain possible.
- The model never directly mutates authoritative state; effects and status changes pass existing validators.
- NPC context is built only from that NPC's role card, own observations, and own committed speech. Unrelated NPC histories are never substituted.
- Preserve campaign gates, time pacing, billing receipts, streaming stages, idempotent request IDs, and existing saves.

## Tasks

### 1. Select engine through configuration

- [ ] Add `runtime.turn_engine` with `single_call` and `multi_agent_beta` values.
- [ ] Set local and online profiles to `single_call`; retain the legacy factory for beta configurations.
- [ ] Route portal campaign and freeform sessions by engine without adding a player-facing toggle.

### 2. Assemble one bounded scene context

- [ ] Create a deterministic context projector that selects nearby/relevant NPCs and reads each through `agent_context_entries(game_id, actor_id)`.
- [ ] Include player-visible worldbook, public scene state, current goal, recent player prose, status bounds, and script anchors within a bounded input budget.
- [ ] Keep raw private material out of the player context and avoid including unrelated NPC memories.

### 3. Generate and commit a turn

- [ ] Define a structured scene response with decision, prose, dialogue, action outcome/effects, bounded status changes, and three optional actions.
- [ ] Call the model once with no tool loop. Validate actor IDs, locations, effects, status bounds, duration, and options before committing.
- [ ] Persist the proposed result on the player event so retries can resume without another generation. Queue deterministic NPC-speech work to give every speaker an independent event history.
- [ ] Keep novel output in second person and interactive output as labeled NPC dialogue blocks.

### 4. Remove ordinary-turn follow-up model calls

- [ ] In single-call mode, disable campaign scene/novel model presenters, NPC model writers, separate status adjudication, and the follow-up action model.
- [ ] Read the single result's status and options from committed details. Use authored text/leads for scripted choices, continuation, and time advances.
- [ ] Keep beta multi-agent paths unchanged.

### 5. Verify and release

- [ ] Add focused tests for one model invocation, actor isolation, world-effect validation, replay, and beta selection.
- [ ] Run the relevant backend suite and frontend build once after the integrated version is ready.
- [ ] Run a bounded real-model smoke with a fresh disposable save, inspect billing `model_calls`, then push and deploy the online profile.
