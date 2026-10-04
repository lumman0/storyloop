# Story Pacing and Identity Implementation Plan

**Goal:** Make day-one story replies concise and consequential, explain the nameplate rule, and keep stranger identity aligned with what the player has learned.

**Architecture:** Preserve one model call per turn. Add a small identity sidecar to opening and turn schemas, validate and persist it with the scene event, and project it into the next prompt and cast API. Version the winter scenario separately.

**Tech Stack:** Python, Pydantic, existing event store, pytest, source-driven scenario JSON.

## Global Constraints

- No extra model call per turn.
- No procedural state machine for ordinary actions.
- Existing saves remain readable.
- Keep the private scenario outside the public repository.

## Tasks

1. Add optional encounter evidence fields to generated opening and turn results; initialize and persist the player's seen and named actor IDs.
2. Project player knowledge into the turn model and use it for source-driven cast visibility, with a legacy fallback for older saves.
3. Revise generic opening and turn instructions for rule clarity, natural first meetings, compact prose, and advancing options.
4. Copy the winter scenario to v11; correct the day-one nameplate facts and opening focus, then update the private catalog.
5. Run focused offline checks, inspect a real new-save sequence, and deploy the verified code and private package.
