# Activity continuity implementation plan

**Goal:** Keep ordinary turns grounded in player identity and evolving activity state, and publish a revised romance scenario without changing existing saves.

**Architecture:** Extend optional mutable-field transition validation and context projection; refine single-call option selection; create a separate private scenario version with authored stages and delayed identity reveal.

**Tech Stack:** Python, Pydantic, AgentScope, SQL game store, JSON scenario packages.

## Tasks

1. Add optional `transitions` to declared mutable state, expose allowed next values to the model, and reject skipped or reversed stages in the existing effect validator. Add one focused transition test.
2. Add player profile, public rules, recent prose and recent suggestions to single-call context. Require generated options to follow the committed activity result rather than reusing stale scene leads. Add one focused option regression.
3. Create a private immutable romance package revision with name-only introductions, public visual/social details, a Day 3 identity reveal, and a multi-stage Day 1 meal. Keep the previous version for old saves and retire it from the public catalog.
4. Validate package loading and run the focused/full backend checks and frontend build. Push only the harness code; transfer the private package separately. Deploy and verify with a disposable save and health check.
