# Prepared Story Start Implementation Plan

> **For agentic workers:** Implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make source-driven save creation read prepared story assets with no model call.

**Architecture:** Keep source facts and turn generation unchanged. Extend the blueprint/package contract for prepared opening options and player identity choices; render the template and copy fixed NPC profiles into save state. Prepare a new immutable private winter version with complete cast cards and opening.

**Tech Stack:** Python, Pydantic, existing event store, private JSON scenario package, React API consumer.

## Global Constraints

- New saves must not call a model during opening.
- Existing saves remain bound to their original package versions.
- NPC secrets stay in server-side cards; player-visible identity remains gated by encounter state.
- No private scenario materials or credentials enter the public repository.
- Keep verification focused until the version is complete.

---

### Task 1: Prepared source contract

**Files:** `src/story_harness/world/story_blueprint.py`, `src/story_harness/world/scenario.py`, `tests/test_story_blueprint.py`.

- [ ] Define bounded random player profile choices and three opening actions in the blueprint.
- [ ] Read fixed actor public profiles from the package and validate named cast integrity.
- [ ] Confirm source packages with incomplete start assets fail before publishing or entering the catalog.

### Task 2: Model-free save creation

**Files:** `src/story_harness/portal/service.py`, `src/story_harness/portal/user_scenarios.py`, `tests/test_source_driven_save.py`.

- [ ] Select a prepared player profile or apply custom fields, render explicit opening placeholders, and seed actor profiles and player knowledge.
- [ ] Return the prepared opening and actions without constructing a model.
- [ ] Reuse the existing publish-time prologue generation only if a creator omits a prologue, then validate the resulting package before publication.
- [ ] Verify create/resume and custom/random setup with a model factory that fails if called.

### Task 3: Winter fixed cast and verification

**Files:** private winter scenario version under `D:/ai/romance-validation-private`, private catalog, focused test fixtures.

- [ ] Prepare a new package version with complete named cards, visible profiles, player identity choices, and coherent opening options.
- [ ] Validate the package and a local new save, then run the relevant Python tests and frontend build if affected.
- [ ] Review public diff for private material and secrets before commit or deployment.
