# User Scenario Upload Implementation Plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

**Goal:** Let signed-in authors upload a valid ZIP scenario, keep it private as a draft, publish it for their own play, and retain old published versions for existing saves.

**Architecture:** SQL stores ownership, metadata, and immutable version references. A local package store writes validated ZIP contents under a persistent directory; `UserScenarioService` exposes draft and published listings to the portal. The browser sends a bounded multipart ZIP upload and displays the author's uploads. The storage boundary stays replaceable with OSS later.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, Python zipfile, React/TypeScript.

## Tasks

- [x] Add migration and repository tests for owned scenarios and versions.
- [x] Add ZIP validation tests for size, traversal, symlinks, malformed package, and a successful package.
- [x] Implement upload, author listing, private publishing, and catalog/save integration.
- [x] Add authenticated HTTP endpoints and integration tests.
- [x] Add a responsive author upload page and navigation; verify TypeScript build.
- [x] Mount a persistent upload directory in ECS and document format, limits, and visibility.
- [x] Run full backend/frontend checks and inspect the final diff.
