# Structured Romance Web Implementation Plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

**Goal:** Make a private romance campaign playable in the browser from opening through a saved ending, with readable, structured story responses.

**Architecture:** The runtime emits ordered, player-visible presentation segments alongside its legacy text. The portal serializes these segments and the current campaign gate into its existing save and turn responses. The React reader renders segments and submits gate choices through the existing turn endpoint. Scenario content remains in the private local catalog and package.

**Stack:** Python, AgentScope, FastAPI, SQLite, React, TypeScript.

## Constraints

- Keep `body` and the existing `/choose` and `/next` commands for CLI and old clients.
- Store no API key or private scenario content in the public repository.
- Use the campaign program for option IDs, labels, recipient eligibility, and gate type.
- Keep persisted turns replayable and older responses readable.

## Task 1: Runtime presentation contract

- [x] Add an ordered segment value object with kind, text, and optional speaker metadata.
- [x] Build freeform narration and dialogue segments from visible observations in one pass; retain legacy narration.
- [x] Carry ordered campaign scene, message, dialogue, and prompt segments through gate processing.
- [x] Verify a multi speaker turn and a campaign choice transition with focused tests.

## Task 2: Portal API contract

- [x] Add `segments` and a player-safe `interaction` gate to save, resume, and turn views.
- [x] Keep historical `body` responses available to old saves; ensure new turns persist the new contract.
- [x] Verify ownership, option eligibility, and response replay through the HTTP adapter.

## Task 3: Browser reader

- [x] Render narration, scenes, private messages, and labeled NPC replies as separate blocks.
- [x] Show choice and message gates as interactive option panels with optional or required custom text.
- [x] Preserve freeform input and recommendations outside gates; display the ending and resumed state.
- [x] Build the frontend and visually inspect the story flow.

## Task 4: Private romance validation

- [x] Use the private local catalog to create a browser save, submit choices, converse with an NPC, resume, and reach day 14 ending.
- [x] Check stored history and the visible reader against API output.
- [x] Run the focused Python suite and frontend build; commit and push only public harness changes.
