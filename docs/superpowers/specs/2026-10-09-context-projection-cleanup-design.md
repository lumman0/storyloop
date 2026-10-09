# Context projection as the active narrative architecture

The current scene engine already projects player and character histories and generates an ordinary turn in one structured model call. Platform still contains the retired per-character ReAct implementation and lazily instantiates it for persisted beta work. Old routing requirements, factories, tests and naming obscure the active architecture.

The approved direction is to remove the one-NPC-one-ReAct capability and focus on context projection. Legacy multi-agent saves are disposable; no migration or continuation compatibility is required. Existing archives remain available in Git history.

## Runtime and boundaries

Keep character identity, recipient-scoped observations/history, role cards, worldbook visibility, token budgeting, deterministic reply delivery, validation, event commits, usage and settlement/replay. A character context is data, not an independently running ReAct agent. A shared scene model sees multiple contexts; this is not hard information isolation.

Harness removes the legacy NPC handler injection and the old player-input helper that creates beta NPC work. Unsupported old `npc_reply` work must be rejected before any model call or world mutation, with an explicit old-save/new-game error; do not silently discard it. The supported `single_npc_reply` queue contains already generated speech and remains intact. This is a pre-1.0 breaking API change: harness becomes 0.2.0, and platform consumes >=0.2,<0.3 at a reviewed immutable Git revision.

Platform removes the legacy agents, legacy session/factory, and unused per-NPC heart-message writer. Campaigns retain batch message generation and their existing scheduling/presentation semantics. Rename active ReAct-specific session names to turn/scene engine names. The old compression manager may be removed if it has no active consumers; persisted character-context records and current context projection remain.

Configuration requires active task routes (`single_turn`, `narration`, `followup_actions`), without fallback to retired `main_react`, `npc_reply`, `npc_selection` or `work_selection` routes. Remove obsolete per-agent iteration settings and dead routes from committed examples/defaults. Preserve other active generation routes and request timeout controls. Existing private configs may contain unused extra legacy keys; do not dump credentials or add a new migration subsystem for them.

## Data and release scope

Inspect known local project data locations for identifiable legacy saves. Only confirmed obsolete save data is eligible for deletion; do not delete complete database files containing accounts, billing or content. Do not touch production services or infer remote deployment access. No automatic deletion occurs on application reads. Record actual local cleanup separately from the removal of compatibility code.

Update active documentation to explain context projection and the legacy-save break. Historical dated specs remain historical. No new multi-agent execution, context summarizer, evaluation platform or memory backend is added in this cleanup.

## Verification

Exercise independent harness source/wheel usage; ordinary scene generation and deterministic replay; character visibility; unsupported legacy work rejected before side effects; campaign batch messages; configuration with only active routes; and platform HTTP/SQL settlement/recovery. Replace tests whose sole subject was retired ReAct behavior, preserving coverage of still-supported semantics. Verify no active imports of the removed modules. Run full backend suites once after targeted checks pass and independent package integration with the new harness wheel. Preserve existing Git tags.

## Follow-on work

1. Make context projection inputs, selected facts, provenance and budget decisions inspectable.
2. Use long-running narrative cases to improve relevant history selection and memory validity.
3. Compare effect, latency and cost on a small stable case set as optimizations are attempted.
4. Extend execution journaling and recovery to earlier failure windows.

These are future work, not acceptance requirements of this cleanup.
