# Story pacing and player identity knowledge

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

The save `df0cbdbe0e9d4e569ccd95d3060e312b` spent three turns and roughly 1,700 Chinese characters on looking at a nameplate, taking it, and a short greeting. The opening did not explain the nameplate's purpose. The narration named strangers before they introduced themselves. This design fixes those causes without adding model calls or procedural steps for small actions.

## Turn contract

The existing single scene call remains responsible for prose, NPC speech, memories, and options. The prompt distinguishes emotional pacing from event pacing: slow romance means trust grows gradually, while the world and programme still move. Short actions get short, consequential replies. Detail earns its place by revealing a person, changing a relationship, clarifying a rule, or moving an activity forward. Each option starts from the committed result; at least two options should lead to materially different next beats, while free input remains available. No fixed action list or automatic milestone completion is introduced.

## Player knowledge

For new source-driven saves, persist two independent sets of actor IDs: people the player has seen, and people whose names the player can connect to a face. The generated opening and every story turn may report encounters with a short, player-visible evidence excerpt. A name becomes known only when the excerpt explicitly introduces the person or identifies the person through an in-world source. A printed name on a table does not identify a face. The server validates IDs and evidence, then updates the sets in the same event as the scene. The cast sidebar uses the named set; older saves without this state retain their previous behavior. The model receives the player's current knowledge and must refer to unidentified people by visible traits until introduction.

## Winter scenario

Publish a new immutable winter package. Its day-one facts and opening focus explain why the programme asks for a blind nameplate choice, what choosing means at the finale, and that the player picks another guest's name. The opening resolves the rules before asking for an action. Once the nameplate is chosen, narration turns toward introductions and the day's programme rather than repeatedly inspecting the card. Preserve v10 for existing saves.

## Validation

Use focused offline checks for identity persistence, cast visibility, and scenario loading. Inspect one generated opening and early turn sequence against the three reported failures before deployment. Model output quality is probabilistic; trace the actual new-save result rather than treating a prompt edit as proof.
