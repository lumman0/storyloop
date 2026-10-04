# Complete actions and selective memory implementation plan

**Goal:** Let one player action produce a complete scene while preserving only notable NPC experiences.

**Architecture:** Keep event-sourced action history; add a small optional recipient-scoped memory field to the single-call result. Retire the romance meal phase graph in a new private package revision.

**Tech Stack:** Python, Pydantic, AgentScope, SQLite/PostgreSQL, JSON scenario packages.

## Tasks

1. Add a focused regression in `tests/test_single_call.py`: one action result with a notable NPC memory must commit one `shared_experience` observation for that participant, none for bystanders, and replay without a second model call. An ordinary action creates no such observation.
2. Extend `SceneTurn` with optional concise participant memories. Validate recipients against on-site target NPCs, save observations on the player action event, and keep them out of the player-visible output. Update the generation prompt to complete the scope of an action in one turn and emit memories only for notable shared facts.
3. Create `winter-show-v9` outside Git from v8. Remove `meal_phase`, its mutable transitions and background cue. Adjust public cooking text, scene goal, and leads so a whole meal can happen in one response. Retire v8 only for new saves; retain v7/v8 packages.
4. Run focused and full backend checks, load the private catalog, perform one disposable model turn, push only public harness code, deploy the API and private v9 package, then verify service health and old package access.
