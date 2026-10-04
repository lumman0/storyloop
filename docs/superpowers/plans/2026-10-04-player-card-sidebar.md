# Player Card Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the save's generated player identity in the reader sidebar.

**Architecture:** A save-scoped read endpoint projects the persisted `player_profile` into bounded display fields. The reader fetches it separately from NPC cast data and renders a reusable side panel.

**Tech Stack:** Python/FastAPI, React/TypeScript, CSS, unittest.

## Global Constraints

- No additional model call or player point charge.
- Keep old saves without `player_profile` playable.
- Enforce save ownership before returning profile data.
- Do not mix player identity with Mem0 preferences or NPC cast.

---

### Task 1: Project a player's saved card

**Files:**
- Modify: `src/story_harness/portal/service.py`
- Modify: `src/story_harness/portal/http_api.py`
- Test: `tests/test_source_driven_story.py`

**Interfaces:**
- Consumes: `accounts.resolve_token(token)`, `accounts.get_save(player_id, game_id)`, `store.load(game_id).data["player_profile"]`.
- Produces: `PlayerPortal.player_card(token, game_id) -> {"name": str, "fields": [{"key": str, "value": str}]}` and `GET /v1/saves/{game_id}/player-card`.

- [x] Add a focused assertion to the existing offline opening test for the generated name and appearance, and assert that another account cannot read the card.
- [x] Run `python -m unittest tests.test_source_driven_story -v`; confirm the assertion fails because the route does not exist.
- [x] Implement the projection, ownership check, and HTTP route. Return `{"name": "", "fields": []}` for saves without a player profile.
- [x] Run the focused test again and confirm it passes.

### Task 2: Render the player's card

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/pages/PlayPage.tsx`
- Create: `web/src/components/PlayerCardPanel.tsx`
- Modify: `web/src/styles/reader.css`
- Modify: `web/src/styles/responsive.css`

**Interfaces:**
- Consumes: authenticated `GET /v1/saves/{game_id}/player-card`.
- Produces: player card panel before `CastPanel`, with loading, retry and missing-profile handling.

- [x] Add TypeScript API types and fetch method; load on game/state change.
- [x] Render name and all returned fields with known Chinese labels and a generic fallback for script-specific keys.
- [x] Match existing sidebar spacing, show the card before the prologue on narrow screens, and wrap long text.
- [x] Run `npm run build` from `web` and confirm exit 0.

### Task 3: Final review

**Files:** All files above.

- [x] Run focused Python test and web build with fresh output.
- [x] Inspect `git diff --check` and changed files for accidental private data.
- [x] Commit the feature in this isolated worktree.
