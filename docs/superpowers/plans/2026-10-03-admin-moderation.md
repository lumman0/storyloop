# Administration and Scenario Moderation Implementation Plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

**Goal:** Add server-enforced player, reviewer, and administrator roles; immutable version review; public scenario listings; and a management UI without changing story runtime semantics.

**Architecture:** Keep authorization and moderation in `portal`. The existing private publication remains author-only. Review submissions snapshot a package version and display metadata. Approval creates a public release; listing and save access resolve through a centralized visibility policy. Audit records are append-only.

**Tech stack:** FastAPI, SQLAlchemy/Alembic, React/TypeScript, SQLite/PostgreSQL.

## Constraints

- Preserve existing accounts, saves, private published scenarios, and package hashes.
- No default web-created administrator. Bootstrap an existing account from a server CLI.
- Reviewer access applies to submitted versions, not private drafts or player saves.
- Authorization is checked on every request by the API; frontend navigation is only presentation.
- Avoid model calls for moderation by default. Approval is a human decision.

## Tasks

1. Add migration for roles, account status, review submissions, public releases, and append-only audit records. Add centralized capability policy and admin bootstrap CLI. Verify unauthorized, suspended, and last-admin cases.
2. Add author submission and version upload services, exact-version review decisions, and public catalog resolution. Verify author isolation, competing decisions, content hashes, and old-save behavior.
3. Add authenticated management endpoints for queue/detail/decisions, users/roles/status, releases, and audit history. Preserve cookie and Origin rules.
4. Add author status/actions and capability-gated management pages. Validate backend responses, build frontend, and run the focused and full test suite after the complete slice.
