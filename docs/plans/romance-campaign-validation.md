# Romance campaign validation

## Goal

Run a 14-day, CLI-only romance show from arrival through a player-dependent finale. Keep the source document and adapted scenario outside the public harness repository.

## Runtime boundary

- `GameSession` remains responsible for free-form ReAct turns and NPC dialogue.
- A data-driven `CampaignSession` advances time, applies scheduled scene events, pauses at player choices, and resolves the ending. It commits all changes through `GameStore`.
- Private campaign JSON and character cards live under `D:\ai\romance-validation-private`. Generic orchestration code and tests live in this repository.
- A single `cursor` in campaign state makes a scheduled step idempotent. Choices are explicit, while ordinary dialogue and `/next` advance the background clock.

## Verification

1. Offline tests cover gate ordering, background progression, private messages, NPC knowledge isolation, and two different finales.
2. An offline full-season script plays all 14 days and records the event trail.
3. An offline AgentScope integration run samples main/NPC ReAct dialogue without external model calls. Live model validation requires explicit authorization to send the private scenario context to the provider.

## Source decisions

Use the source's master 14-day timetable when its detailed paragraphs disagree: newcomers enter on day 3; heart messages start on day 2. The adapted cast and dialogue are original and kept private.
