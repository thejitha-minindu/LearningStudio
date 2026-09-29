# Verification record

Verified locally on Windows on 2026-09-27 with Python 3.12 and Node 24.

| Check | Result |
| --- | --- |
| Backend controlled test suite | 50 tests pass; isolated SQLite databases, no paid providers |
| Alembic initial migration | Applied successfully; `alembic check` reports no drift |
| Migration round trip | Upgrade, downgrade, re-upgrade tested on a temporary database |
| PostgreSQL schema | DDL compiles for PostgreSQL; database server execution not verified |
| Frontend TypeScript | `npm run typecheck` passes |
| Next.js production build | Passes using official SWC WebAssembly fallback and webpack on this Windows host |
| No-document HTTP demo | Actual API + separate persistent worker produced 3 fixture sources, 60-minute plan, cited lesson, persisted assessment and next step |
| Exam HTTP demo | Uploaded authored syllabus and two text PDFs; 6 supplied/fixture sources, supplied-scope plan, cited lesson and persisted assessment |
| Frontend proxy integration | Exam demonstration also passed through `/api/backend`, including multipart uploads, persistent processing, citation retrieval and assessment |
| Browser flow | Submitted no-resource task, observed ready plan, opened exact passage, submitted wrong choice, observed needs-support state and generated support lesson |
| Real public retrieval | Fetched official Python tutorial HTML through the public-only fetcher, checked robots, extracted 16 passages |
| Tavily live search | **Not run**: no API credential configured |
| Gemini live generation/grading/audit | **Not run**: live credentials and model access were not verified during the original audit |
| Docker Compose + PostgreSQL services | **Not run**: Docker is unavailable on this host |

The controlled provider tests inspect real-adapter HTTP request shapes and supply mocked
responses. They verify error handling, bounded retries, malformed responses and untrusted-data
prompt separation. They do not establish account access, model compatibility, live educational
quality, or semantic support accuracy. The real public retrieval test is **only** an HTML
fetch/extraction smoke test, not live research or generation.

The backend suite emits one upstream Starlette deprecation warning about its httpx-based test
client. This does not affect test results. Fixtures are labelled throughout the UI, API and
stored lesson provenance. All verification uses authored example inputs, not personal documents.

The Windows native SWC binary was blocked by Application Control. `frontend/scripts/next.cjs`
selects the installed, official, version-matched WASM package on Windows. It uses the
`NEXT_TEST_WASM_DIR` hook found in Next 16.3.6's loader because that version's ordinary installed
WASM-package resolution failed on this host. Next and the WASM package are pinned together;
review this workaround when upgrading. Linux builds use the ordinary compiler selection.

Reproduce the HTTP demonstrations with `scripts/demo.py` and `scripts/demo.py --exam`.
The included UI screenshot is at `docs/images/learning-demo.png`;
`artifacts/` is excluded from version control.
