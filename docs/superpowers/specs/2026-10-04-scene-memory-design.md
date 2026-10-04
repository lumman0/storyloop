# Complete actions and selective shared memory

The default story turn should follow the scope of the player's action. If the player chooses to cook a meal, one generated response may cover the cooking and its immediate social outcome. The system must not split that activity into mandatory ingredient, stove, and serving turns. A player who asks to do only one step should still receive only that step.

The authoritative event log already stores player input and the model's visible scene. Keep that log as the record of ordinary activities. Do not introduce a separate procedural state field for each routine activity. Scripted choices, time, knowledge boundaries, and durable objects retain their existing structured state where necessary.

One optional, concise shared memory may be emitted for each involved NPC in the same structured scene result. It records only a notable fact both the player and that NPC experienced, such as an intimate moment, promise, or conflict. The runtime validates the NPC is an on-site participant and commits the memory as a recipient-scoped observation on the same event. Routine actions need no extra memory. The memory is not another player-visible message or model call. It enters that NPC's existing context and later compression, while the player already has the full scene observation.

The romance scenario gets a new immutable version. Remove its meal phase transition graph and automatic meal completion cue, replace kitchen microstep prompts with a whole-activity choice, and keep the later dinner scene neutral about who prepared the food. The prior scenario packages and saves remain readable. Validate with a focused memory persistence check and one isolated real-model action, then deploy the new package for new saves.
