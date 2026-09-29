# Implementation plan

The starting repository was empty. No applicable AGENTS.md was found.

1. Define strict task/provider contracts and SQLAlchemy persistence; add Alembic migration.
2. Add bounded research, explicit resource authorization, extraction and passage provenance.
3. Build purpose-specific curriculum, budgeted planning, cited generation and separate support audit.
4. Persist assessments and conservative topic evidence; queue adapted lessons.
5. Connect a Next.js demonstration, test both resource routes and safety boundaries, and document the integration.

One FastAPI application and one worker share a database. PostgreSQL is the Compose default;
SQLite is supported for local tests and a single-worker, credential-free demonstration.
No surveillance, filesystem scanning, calendar integration, or goal-management functionality is included.
