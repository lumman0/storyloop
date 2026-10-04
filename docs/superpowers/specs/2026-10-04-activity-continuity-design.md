# Activity continuity and delayed reveals

The default single-call engine must carry player identity, public rules, recent prose, and recent suggestions into every ordinary turn. Each NPC still receives only its own stored observations and role card. The model proposes a scene, but declared mutable fields remain the authority for activity progress.

An optional `transitions` map on a mutable field restricts its next value based on its current value. This lets a script model a multi-step activity without hard-coding cooking, dates, or any other specific scene into the harness. The projector sends only currently allowed next values. Invalid proposals are discarded before an event is committed.

The single-call engine should use generated next actions from the committed turn. It must not refill a completed activity's menu with unchanged authored leads from an earlier scene. Recent suggestions and player actions are supplied to the next generation to reduce semantic repetition. If the model provides fewer valid actions, the interface shows fewer buttons; free input remains available.

The winter romance package will be revised as a new immutable version. The old package and saves remain available, while only the new version appears for new games. The new opening introduces names and observable appearance before occupations or ages. Program production, a casting premise, filming boundaries, and the delayed reveal are stated in public rules. A Day 1 meal has declared stages and timed background cues, so the player can participate in preparation and dining, while other guests can complete it if the player chooses something else. Day 3 explicitly reveals ages and occupations.

Validation uses a focused transition and option regression, the existing backend suite, package loading, and one disposable model turn. Existing player saves are never rewritten.
