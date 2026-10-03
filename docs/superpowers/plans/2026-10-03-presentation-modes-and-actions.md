# Presentation Modes and Follow-up Actions Implementation Plan

> **For agentic workers:** Implement in the existing isolated worktree. The user requested a focused verification pass after the full feature, rather than a test for each small edit.

**Goal:** Support interactive and novel presentation for the same authoritative game loop, then offer three clickable, model-suggested player actions after ordinary turns.

**Architecture:** A versioned scenario manifest selects the presentation mode. The ReAct runtime still commits NPC and world events; novel mode withholds raw streaming segments and passes visible beats to one second-person presenter. An independent cheap-model advisor sees only the final player-visible story and returns optional actions. Campaign gates use their existing validated controls.

**Tech Stack:** Python, AgentScope, FastAPI, React, TypeScript.

## Tasks

- [x] Add manifest validation and mode propagation without changing campaign/freeform semantics.
- [x] Compose novel prose once after committed turn results, suppressing earlier raw dialogue segments in the stream.
- [x] Add a single cheap-model call for three follow-up actions, with validation and safe fallback.
- [x] Add API types and clickable option buttons while preserving free text and mandatory gates.
- [x] Verify focused backend contracts, frontend build, and offline smoke turns; inspect the diff for secrets and unintended changes.
