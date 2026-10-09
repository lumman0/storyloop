# Pluggable Scenario Storage Implementation Plan

> Historical planning record: paths and commands describe the pre-split repository, not current installation instructions.

**Goal:** Keep local scenario deployment working while making catalog metadata and published package storage independently replaceable.

**Architecture:** `ScenarioCatalogSource` returns published listing metadata. `ScenarioPackageStore` materializes a package reference as a local read-only directory for the existing runtime. `GameCatalog` validates and fingerprints the materialized package on load and access. The local adapters keep the existing JSON catalog and filesystem package format. A later PostgreSQL source and OSS store can implement the same interfaces without changing the runtime or save schema.

**Tech Stack:** Python 3.12, SQLAlchemy-backed existing saves, unittest.

## Constraints

- Keep existing `GameCatalog.load(path)` and `PlayerPortal(catalog_path, ...)` entry points working.
- Preserve package ID, version and SHA-256 checks for saves.
- Keep local catalog paths compatible with existing administrator-managed JSON files.
- Do not add a cloud SDK or credentials until the OSS implementation is requested.

## Tasks

1. Add a failing test that injects independent catalog and package providers, then implement the two protocols and local providers.
2. Add a failing test for a package moving to a new local cache directory between catalog load and access; make `GameCatalog.get` materialize and verify the current directory.
3. Document the local deployment contract and future PostgreSQL/OSS adapter contract; run catalog and portal tests plus the full backend suite.
