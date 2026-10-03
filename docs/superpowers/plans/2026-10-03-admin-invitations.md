# Administrator Invitations Implementation Plan

**Goal:** Let administrators issue and manage registration invitations during the private test while retaining a narrow policy boundary for later player issuance after a first completed turn.

**Architecture:** Keep invitation persistence in `portal`, separate from game runtime and credits. The database stores only hashes of one-time codes. An invitation service checks issuance policy and records the issuer, usage, expiry, revocation, and management audit. The API returns plaintext codes only on creation; the management page shows them until the page is left or refreshed.

**Stack:** Alembic, SQLAlchemy, FastAPI, React/TypeScript, SQLite/PostgreSQL.

## Scope

- Internal test: administrators can issue 1–20 codes per request; each code expires in 30 days and works once.
- Public test policy (later): a player becomes eligible after a first successful game turn. No player issuance endpoint is enabled now.
- Preserve existing invitations and the server CLI. Previously issued codes keep their existing validity and usage state.
- List only metadata after creation; never persist or log plaintext codes.

## Tasks

1. Add nullable issuer, creation, and revocation fields to the existing invitation table; keep prior rows intact.
2. Add invitation service with administrator-only issuance/list/revocation, transactionally recorded audit, and registration rejection for revoked codes. Cover access and single-use behavior in one focused integration test.
3. Add API endpoints and management page tab with count control, one-time code display/copy, and status listing. Build the frontend.
4. Run the focused and full checks, commit as `lumman0`, push, back up the ECS database, deploy, and verify migration and access controls without creating a production code on the user's behalf.
