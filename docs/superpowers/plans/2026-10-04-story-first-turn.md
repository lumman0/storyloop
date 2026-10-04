# Story-first Turn Implementation Plan

> **For agentic workers:** Execute inline in this session. Keep changes focused and verify before claiming completion.

**Goal:** Make the default single-call engine narrative-first while retaining player recall and independent NPC contexts.

**Architecture:** Replace the broad model-facing `SceneTurn` schema with a small `NarrativeTurn` contract. Adapt its optional sidecar into the existing persistence format so prior saves and portal clients remain readable. Prune only prompt fields that steer routine narrative into fixed mechanics.

**Tech Stack:** Python, Pydantic, AgentScope, SQLite test store.

## Global Constraints

- One model call per ordinary turn.
- Do not split player actions into fixed phases.
- Keep the displayed story untouched by sidecar validation.
- Keep NPC contexts recipient-scoped; do not add private source content to other actors.
- Preserve old-save replay and the beta engine.
- Add only focused regression tests; the user prefers a full test pass after the version is complete.

---

### Task 1: Minimal model contract and context

**Files:** `src/story_harness/agents/scene_turn.py`, `tests/test_single_call.py`

- [x] Add a focused failing test that the model-facing call uses `NarrativeTurn`, whose required content is the story, and that projected context omits mutable transition menus and stale option lists.
- [x] Run that test to confirm the failure.
- [x] Add `NarrativeTurn` and a short story-first prompt. Keep player/NPC history, current scene, and public rules. Remove workflow-like context fields from the model request.
- [x] Run the focused test.

### Task 2: Persist without rewriting prose

**Files:** `src/story_harness/runtime/single_call.py`, `tests/test_single_call.py`

- [x] Add a focused failing test in which optional sidecar metadata is invalid but the model's complete story remains the player-visible text, and a notable event reaches only its participant.
- [x] Run that test to confirm the failure.
- [x] Adapt the minimal turn to the existing event format. Do not allow action validation, authored action rules, or worldbook lookup to replace its prose. Save only validated, actor-visible NPC observations.
- [x] Run the focused test and then the complete suite once.

### Task 3: Real-model quality and documentation

**Files:** `docs/user-scenarios.md`

- [x] Update the description of the default engine.
- [ ] Run one isolated real-model compound-action check against the winter scenario when explicitly authorized. Automatic approval review rejected the attempted private scenario/API-key egress; do not retry without the user's specific authorization.
- [ ] Review the diff, commit only public harness code, and report remaining narrative limitations accurately.
