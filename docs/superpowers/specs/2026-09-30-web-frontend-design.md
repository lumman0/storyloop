# Web frontend design

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

## Goal

Provide a browser interface for the existing single-player story platform. A player can register or log in, browse a game catalog, create or resume a save, read the story transcript, submit an action, and see suggestions in a separate region.

## Boundary

The frontend is an independent React application in `web/` in the same repository. It talks only to the versioned FastAPI JSON API. The Python portal owns accounts, saves, game state, and agent execution. The browser never receives model credentials. Vite proxies `/v1` to the local API during development; online deployments configure an API origin and allowed CORS origins separately.

## Experience

The catalog is the landing screen after login. It takes visual cues from Tipsy's dark, story-forward gallery without copying its code, imagery, or text. A save list provides clear resume actions. The reading screen gives story prose priority, shows player actions distinctly, and keeps progress and recommendations outside the story text. Forms, loading, empty, and error states work on desktop and mobile.

## API extension

Catalog entries may include optional summary, genre, and theme fields. A save history endpoint returns the persisted opening view plus ordered player turns and their responses, scoped to the authenticated owner. New records keep the raw player input alongside the existing hash and response so reloads recreate the transcript. A migration adds the necessary columns/table for SQLite and PostgreSQL; existing saves remain readable with a scenario-opening fallback.

## Quality

The frontend uses TypeScript, Vite, React, and small reusable shadcn-style components. Session credentials are kept in browser session storage for this version. A meaningful API ownership/history test and a production frontend build verify the complete flow. The public repository contains only generic sample games and original UI assets.
