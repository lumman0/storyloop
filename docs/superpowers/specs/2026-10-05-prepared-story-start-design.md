# Prepared story start

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

The source-driven scenario path currently creates a new prologue, player identity, and nine NPC cards during every save request. The winter source document defines cast constraints but no complete cast; the winter v11 package therefore contains generation prompts in its NPC cards. This adds roughly 30 seconds before the player sees the opening and lets the cast vary between saves.

For a prepared scenario version, the published package owns the opening template, opening options, complete named NPC cards, and a small pool of player identities for random start. Custom player setup overrides a local default identity. Save creation selects a player identity, renders explicit player placeholders in the opening, copies the package cast into save state, and persists the result without a model call. A version without these prepared assets must be completed or rejected before it becomes playable; it must not silently fall back to generation during save creation. Existing saves remain bound to their original package versions.

The private winter version will reuse its established named cast and images, update the NPC cards to complete identities, and supply an opening that explains the show, the nameplate rules, and the first meaningful choice. The source blueprint still provides story facts and milestones. Ordinary turns keep their existing single model call and scoped NPC memories. The opening does not reveal which stranger matches a printed name until the story establishes that knowledge.

Validation checks that actor IDs, names, cards, opening options, and random player identities are complete and unique. A focused save test proves that creating and resuming a prepared save makes zero model calls, preserves cast identity, and accepts custom player details. An online start after deployment may be verified without invoking the model.
