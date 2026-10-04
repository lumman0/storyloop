# Story-first turn design

The default one-call engine should preserve the quality and scope of a direct DeepSeek story response. The harness contributes relevant earlier events and recipient-scoped NPC knowledge; it does not make the model complete a workflow of action phases or state fields before telling the story.

## Turn contract

1. Project only the current scene, public rules, the player's relevant history, and each relevant NPC's own context. Keep NPC private entries separately labeled. Do not send mutable-state transition menus, status delta menus, old suggested options, or fixed action leads as narrative obligations.
2. Ask the model to write the full response to the player's entire input in one call. The generated prose is the primary result. A small sidecar identifies participants, how they interacted, their own spoken lines, optional next actions, and noteworthy memories. All sidecar fields except prose may be absent.
3. Display the prose as generated. Sidecar validation may drop invalid metadata but must not replace or truncate the prose. A routine activity is one turn, even if it includes several natural subactions.
4. Store the player's original input and the resulting prose. Store an NPC's own speech and notable shared events only in that NPC's context. A bystander sees only a perceptible event, never another NPC's private context or the player's unspoken inner state.
5. Keep campaign gates, deterministic timing, billing, and old-save replay compatible. The prior multi-agent engine remains optional beta. Structured status updates and state transitions are not part of the default model output.

## Quality checks

Use focused contract checks for prose preservation, one-call replay, and scoped NPC memory. Compare at least one real model turn with the user's direct-DeepSeek example, including a compound activity. The model can still write a weak response; the harness must not make that failure more likely by requiring procedural microsteps or overwriting the story.
