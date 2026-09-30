# Web Frontend Implementation Plan

**Goal:** Deliver a playable browser interface backed by the existing FastAPI portal.

**Architecture:** `web/` is a separately built React application and uses the `/v1` JSON API. The portal gains only catalog presentation fields and authenticated transcript retrieval.

**Tech Stack:** React, TypeScript, Vite, shadcn-style primitives, FastAPI, SQLAlchemy, Alembic.

## Tasks

1. Extend portal catalog metadata and persist opening and turn text. Add a migration and an owner-scoped history route.
2. Build the React application with authentication, catalog, save selection, and game reader screens. Keep API calls in one client module and persist only the session token in session storage.
3. Configure local proxy and online API origin, document both start commands, then run focused API tests and a production frontend build.

## Verification

- History returns the opening and turn transcript in order and denies access to another player's save.
- `npm run build` succeeds and the browser can complete login, create/resume, and play flows against the local API.
