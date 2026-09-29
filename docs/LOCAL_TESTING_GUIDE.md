# Local Testing Guide

This is a standalone learning-module prototype, not the larger goal-assistance system. It accepts a learning task, builds a plan and lesson, assesses answers, and recommends next steps. It does not track laptop activity or schedule reminders.

## Audit Summary

| Requirement | Implementation evidence | Verification performed | Status | Remaining issue |
|---|---|---|---|---|
| Accept goal, objective, purpose, prior knowledge, time and resources | Learning Studio form submits these fields to FastAPI; validated in `contracts.py` | UI proxy and API task creation exercised | Verified working | The UI has one prior-knowledge field; the API accepts multiple topics |
| Research without documents | `research.py` calls Tavily in live mode; `fixtures.py` supplies authored corpus entries in fixture mode | Fixture flow ran; live mode without credentials failed visibly before research | Blocked by configuration | Successful live Tavily/Gemini flow remains unverified |
| Use supplied material and supplement gaps | Upload extraction stores sources and passages; research searches uncovered topics | Syllabus and two PDF uploads processed; six supplied/fixture sources observed | Partially implemented | Live web supplementation was not run; fixture supplementation is authored material, not external research |
| Tailor scope to long-term, exam or practical purpose | Purpose reaches curriculum and lesson generation; exam scope is `supplied` or `provisional` | Existing tests cover all three purposes; both exam-scope states exercised | Partially implemented | Fixture lessons are fixed English demonstrations; quality of live tailoring is unverified |
| Find prerequisite gaps | Curriculum records prerequisites; assessments update topic state and can target an unmastered prerequisite | Wrong choice set `needs_support`; support lesson was generated | Partially implemented | No separate diagnostic engine; quality of prerequisite selection depends on curriculum/provider output |
| Plan within time and revise remaining work | `build_plan` applies deadlines, attempted lesson estimates, session limits and deferrals | 120-minute input stayed within budget; reduction to 20 minutes recalculated work; tests passed | Verified working | Durations are estimates, not measured study time |
| Generate lessons with traceable evidence | Lessons cite stored passage IDs; UI opens stored passage and original reference | Resolved citations and opened exact fixture passage | Partially implemented | Fixture content is authored; live citation correctness and semantic support were not verified |
| Assessment changes future teaching | `update_state`, `recommendation` and support jobs connect assessment to later instruction | Incorrect objective answer changed state and plan, then produced a focused support lesson | Verified working | Fixture short-text grading has low confidence; one correct answer does not establish mastery |
| Persist tasks, plans, lessons and attempts | SQLAlchemy tables and Alembic migration store the workflow | SQLite records survived API and worker restart | Verified working | PostgreSQL/Compose runtime was not verified because Docker Engine was unavailable |
| UI is connected to backend | Next.js `/api/backend` proxy forwards requests to FastAPI | Browser page returned 200; proxy health/task requests reached API in both modes | Verified working | Local development identity/token is not production authentication |
| Operate independently of parent system or tracking | Standalone FastAPI, SQL worker and Next.js app; no tracking integration | Full local task flow ran without another system | Verified working | Scheduling and larger goal management are intentionally out of scope |

### Verification Run Here

- Backend: 50 tests passed. Pytest emitted an upstream Starlette/httpx deprecation and could not write its optional cache under the protected default cache path; assertions passed when its temporary directory was placed under `artifacts/`.
- Database: Alembic migration upgrade and `alembic check` passed on an isolated SQLite database.
- Frontend: `npm run typecheck` and `npm run build` passed.
- Runtime: fixture no-document and supplied-exam flows completed; API health, UI proxy, citation lookup, assessment/support adaptation, provisional exam scope, invalid URL rejection, unsupported-file rejection and persistence across API/worker restart were checked.
- Live-mode failure: the original OpenAI-backed run failed before producing a lesson. The generator has since been changed to Gemini; successful Gemini generation/grading/audit and live Tavily search have not been verified. Curriculum generation runs before Tavily search, so Gemini is the first live dependency.
- Not verified: successful Tavily search, Gemini generation/grading/audit, educational correctness of live output, and PostgreSQL via Docker. Docker Desktop's engine was not running during the audit.

## What You Need

Open `D:\Knowledge Scraper` in VS Code (`code .` from that folder). Use Windows PowerShell; WSL is not required. Docker Desktop is optional: use it only for the Compose/PostgreSQL route.

Required versions:

- Python 3.12 or newer. This workspace has `.venv` using Python 3.12.14; system `python` is 3.11.15 and is too old for this project.
- Node.js 20.9 or newer and npm. This workspace has Node 24.16.0 and npm 11.13.0.
- Docker Desktop with Compose only if choosing the Docker route. Docker CLI is installed here, but its engine was unavailable during this audit.

Check versions in PowerShell:

```powershell
Set-Location 'D:\Knowledge Scraper'
python --version
node --version
npm --version
docker --version
docker compose version
.\.venv\Scripts\python.exe --version
```

If `.venv` does not exist, install Python 3.12+ and create it with `python -m venv .venv` after confirming `python --version` reports 3.12+. This machine does not have the optional `py` launcher. Do not recreate or replace an existing environment without checking it first.

### Environment Files and Providers

For local SQLite, create the files only if they do not already exist:

```powershell
Set-Location 'D:\Knowledge Scraper'
if (-not (Test-Path 'backend\.env')) { Copy-Item '.env.example' 'backend\.env' }
if (-not (Test-Path 'frontend\.env.local')) { Copy-Item 'frontend\.env.example' 'frontend\.env.local' }
code 'backend\.env' 'frontend\.env.local'
```

In `backend/.env`, change `DATABASE_URL` from the Compose PostgreSQL URL to `sqlite:///./learning.db`. Keep `PROVIDER_MODE=fixture` for a credential-free demo. `frontend/.env.local` should use `BACKEND_URL=http://127.0.0.1:8000` and the same `DEV_API_TOKEN` as the backend. The frontend defaults already match the example development token. Local environment files are ignored by `.gitignore`; keep real credentials there and never paste them into chat.

| Variable | Meaning and when needed |
|---|---|
| `PROVIDER_MODE` | `fixture` (default, no provider credentials) or `live` |
| `DATABASE_URL` | SQLite URL for local single-worker use; Compose uses PostgreSQL at host `db` |
| `DEV_API_TOKEN` | Shared development-only API token; must match the frontend proxy token |
| `GEMINI_API_KEY` | Required in live mode for curriculum, lessons, grading and evidence audit; create a key in Google AI Studio |
| `GEMINI_MODEL` | Gemini model used for JSON generation; `.env.example` uses `gemini-3.8-flash`, subject to account availability and quota |
| `TAVILY_API_KEY` | Required in live mode when research must search for uncovered topics; obtain it from Tavily |
| `BACKEND_URL` | Frontend proxy target; local default is `http://127.0.0.1:8000`, Compose sets `http://api:8000` |
| `CORS_ORIGINS` | Allowed direct browser origins; the normal UI uses a same-origin proxy |
| `MAX_SEARCHES`, `MAX_PAGES`, `MAX_DOWNLOAD_BYTES`, `MAX_PDF_PAGES` | Bounds on research and resource ingestion; defaults are in `.env.example` |
| `REQUEST_TIMEOUT`, `RETRIES`, `CACHE_SECONDS` | Provider/fetch timeout, bounded retries and cache lifetime |
| `RATE_LIMIT_PER_MINUTE`, `JOB_MAX_ATTEMPTS`, `MAX_OUTPUT_TOKENS` | Development request limit, worker retry limit and generation output limit |
| `ALLOWED_RESOURCE_DIR` | Optional backend-local path allowlist; blank disables local-path resources |

Fixture mode is explicitly labelled in the page and task report. It searches an authored in-memory corpus, not the public web, and only has authored neural-network and database topics in English. Supplied files are extracted and stored, but fixture lesson claims cite authored fixture passages. In live mode, the badge says `LIVE PROVIDERS`; the report distinguishes live research and sources. Gemini and Tavily free-tier limits vary and may change. Configure credentials locally in `backend/.env` before starting both backend processes.

## Install and Start: SQLite (Recommended)

This route needs no Docker service and uses one SQLite database shared by API and worker. Run each terminal command from the stated directory.

Install Python packages from the workspace root:

```powershell
Set-Location 'D:\Knowledge Scraper'
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
Set-Location frontend
npm ci
```

**Terminal 1: migrate and start the API**

```powershell
Set-Location 'D:\Knowledge Scraper\backend'
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2: start the persistent worker**

```powershell
Set-Location 'D:\Knowledge Scraper\backend'
..\.venv\Scripts\python.exe -m app.worker
```

**Terminal 3: start the UI**

```powershell
Set-Location 'D:\Knowledge Scraper\frontend'
npm run dev
```

Successful startup shows Uvicorn listening on `127.0.0.1:8000` and Next.js ready at `http://localhost:3000`. The worker normally waits quietly; it logs completed/failed jobs. Open [Learning Studio](http://localhost:3000), [API health](http://localhost:8000/health), or [API docs](http://localhost:8000/docs). Health should return `status: ok` and `provider_mode: fixture` or `live`.

The health handler does not query the database. A successful migration and an actual task request are the database checks. If a task remains `queued`, the worker is not processing it.

### Optional Docker Compose Route

Docker Desktop must be running. From the workspace root, create the Compose environment file if absent, leave fixture mode on for a no-key demo, then start all services:

```powershell
Set-Location 'D:\Knowledge Scraper'
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
code '.env'
docker compose up --build
```

Compose starts PostgreSQL 17, runs Alembic migrations, then starts API, worker and frontend. It exposes the same browser/API URLs. PostgreSQL data lives in the named `learning_data` volume. Stop with Ctrl+C and `docker compose down`; this preserves the volume. Do not use `docker compose down -v` if you want to keep data. Compose is optional for local testing.

## Manual Test Checklist

Use a separate new task for each scenario where a before/after comparison matters. The UI saves only the most recently created task ID in browser local storage; copy the displayed task ID if you need to reopen an older task.

### A. Long-Term Learning Without Documents

1. In Learning Studio set goal to `Learn machine learning` and objective to `Understand how gradient descent trains a simple linear regression model`.
2. Choose `Long-term learning`; set total minutes to `120` and session minutes to `30`; leave deadline and Optional resources empty.
3. Enter existing knowledge `Python basics; basic algebra; derivatives unknown`. In evidence, note that Python and algebra are familiar but derivatives have not been studied. Click **Create learning task**.
4. Wait for `ready`. Inspect Research & plan: budget and planned minutes, prerequisites, deferred topics, scope assumptions, research mode, queries and warnings. Open a lesson's **Source** and compare the stored passage with its claim.

Expected in live mode: live research queries/sources, an allocated plan no longer than 120 minutes, prerequisite treatment for calculus/derivatives as supported by retrieved evidence, and lessons with inspectable citations. A citation resolving is not proof its passage supports the claim.

Fixture limitation: this exact objective is not fulfilled by fixture mode. Its neural-network corpus can choose `Vectors and weighted sums` and does not teach linear regression or derivatives; the report says fixture mode and `live_research: false`. Treat that as a failed content-scope test, not successful independent research. Run this scenario in live mode with valid Gemini and Tavily configuration to test the intended objective.

**Evidence:** the plan, source/passage panel and badge are visible in UI. Use the Research report, `/tasks/{id}`, `/tasks/{id}/plan` and `/tasks/{id}/sources` API responses to distinguish fixture from web sources and inspect budget/query details. Worker logs show completion/failure but do not prove content correctness.

### B. Exam Preparation With Supplied Material

The workspace includes a clearly synthetic syllabus and two authored sample lecture PDFs.

1. Click **Database exam**. Set objective to `Prepare for a database exam covering SQL joins, functional dependencies, and normalization`, purpose to exam, total to `90`, session to `30`, deadline to tomorrow, and prior knowledge to `Basic SELECT queries; struggles with normalization`.
2. Open **Optional resources**. Set role to `Syllabus`, select `examples/syllabus.txt`, and click **Upload selected files**. Change role to `Lecture`, select `examples/lecture-1-keys.pdf` and `examples/lecture-2-joins.pdf`, and upload them.
3. Click **Create learning task**. Wait for ready. Check `Scope: supplied`, assumptions, the 90-minute budget, deferred content, source roles/origins and lesson citations.

Expected: syllabus-led scope; readable page/section evidence from uploads; supplementary evidence for uncovered normalization content; plan no longer than 90 minutes; practice labelled generated, not predicted; no asserted exam weights. The included syllabus explicitly says it is synthetic and has no weighting. In fixture mode, supplementary sources are authored fixture passages, not public sources. Only live mode can verify external supplementation.

**Evidence:** UI source list and passage panel show source role/origin; API `/sources`, `/passages/{passage_id}`, `/plan` and `/tasks/{id}` reveal exact stored provenance, scope and research warnings. Inspect the source text before judging whether the lesson followed it.

### C. Exam Preparation Without a Syllabus

Create a new exam task with no upload or URL, for example `Prepare for a database exam on joins and normalization`. Wait for ready and inspect scope and assumptions.

Expected: `provisional` scope plus an explicit missing-syllabus assumption, not claims about actual questions or topic weights. If it says `supplied`, inspect the resources and start a new task without them.

**Evidence:** scope and assumptions are visible in UI and `/plan`; `/tasks/{id}` identifies supplied resources and research status.

### D. Assessment and Adaptation

1. Before answering, note the task ID, plan topic order/variants, topic state, confidence, and **Progress & next step** reason. The first lesson's choice question is the clearest deterministic test.
2. Choose an incorrect option and click **Check answer**. Inspect the score, explanation and method; then compare the updated topic state, plan and next step.
3. For a high-confidence wrong choice, expect `needs support`, a support recommendation, a five-minute focused-support entry if it fits the budget, and possibly later topics deferred. Click **Create focused support lesson** and inspect its smaller-step explanation and citations.
4. Create a separate task for a correct answer. A correct choice should show positive feedback; one correct response should not label the learner mastered. Mastery policy requires three distinct reliable successes, including transfer.

**Evidence:** feedback and the topic-state/next-step panels are UI evidence. `/progress`, `/plan`, `/lessons` and `/tasks/{id}` show persisted attempt, score/confidence/method, updated plan and support variant. Fixture short-text grading is explicitly a low-confidence keyword demonstration and should not be expected to trigger the same adaptation as a wrong objective choice.

### E. Change the Time Budget

In an existing task open **Suggested study sessions & budget adjustment**. Change revised total to `20` minutes and session length to `15`; click **Recalculate remaining work**.

Expected: remaining/planned metrics are recalculated, entries that no longer fit appear under Deferred content, and the next-step recommendation does not offer excluded work. Already-created lessons remain viewable as history; they are not necessarily in the revised plan.

**Evidence:** compare the UI metrics and plan before/after, or compare `/plan` responses. The API's `PATCH /tasks/{id}/time` accepts total time including already attempted lesson estimates, not extra time to add on.

### F. Persistence

After creating a task, lesson and answer, stop the API, worker and frontend with Ctrl+C in their terminals. Restart them against the same `.env` and database, then refresh the page or enter the copied ID under **Resume a task**.

Expected: task, plan, lessons, answer feedback, topic state and next-step recommendation remain available. For Compose, `docker compose down` and `docker compose up` preserve data in `learning_data`; never add `-v` when retaining it.

**Evidence:** UI task resume is a quick check; `/tasks/{id}`, `/lessons`, `/progress` and `/plan` confirm the persisted records. This audit verified the SQLite route after API and worker restart, not PostgreSQL.

### G. Failure Handling

- Invalid URL: in Optional resources enter `http://127.0.0.1/` and create a task. Expect a visible validation error; no task should be processed. This URL is deliberately loopback and must not be fetched.
- Unsupported upload: make a disposable file outside the repository with `Set-Content "$env:TEMP\learning-unsupported.csv" 'a,b'`. In the file picker choose **All files**, select it, and upload. Expect an actionable unsupported-type error (HTTP 415). Backend accepts PDF, UTF-8 TXT and HTML only.
- Missing live credentials: use a separate local test database and blank provider variables in the API and worker terminals, with `PROVIDER_MODE=live`. The first failure should name `GEMINI_API_KEY`/`GEMINI_MODEL`; expect task status failed and zero lessons, not a fixture lesson. If Gemini is configured but Tavily is blank, the model curriculum call happens first and may use quota before Tavily reports its missing key. Do not run live probes unless intended.

For the missing-key test, stop the normal backend and worker first. These commands use a new database file and do not overwrite the normal database. Run migrations, API and worker from `backend` with the same environment values:

```powershell
$env:DATABASE_URL='sqlite:///./learning-provider-failure.db'
$env:PROVIDER_MODE='live'
$env:DEV_API_TOKEN='local-development-only'
$env:GEMINI_API_KEY=''
$env:GEMINI_MODEL=''
$env:TAVILY_API_KEY=''
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second `backend` terminal set the same variables and run `..\.venv\Scripts\python.exe -m app.worker`. The UI proxy must keep using the matching token and backend URL. Restore normal fixture/live settings by stopping these processes and restarting from the normal environment. The failure database is separate; keep or remove it only when you are sure you no longer need its test data.

**Evidence:** invalid URL and unsupported type errors are visible in the UI; inspect the task error/status via `/tasks/{id}` and worker terminal logs. Live missing-provider errors are task failures, not HTTP failures from task creation; confirm `/lessons` is empty. Never interpret a `ready` task with `fixture` mode as proof of live research.

## Judging Content Quality

- Open each **Source** passage to see the actual stored text, location and source origin; use **Open original source** to reach the source page. Check that the original still contains the relevant material.
- Match each explanation, worked example and answer to its cited passage. A valid source/passage ID proves only that the reference exists. Fixture mode's audit is explicitly uncertain and does not semantically verify claims.
- Compare the lesson's prerequisites, vocabulary, worked steps and question difficulty with the prior-knowledge evidence you entered. Look for unexplained calculus or database terminology when marked unknown.
- Check that essential prerequisites are taught or planned before dependent topics, and that estimated topic/session minutes plus deferred topics fit the remaining budget.
- For adaptation, compare topic state, confidence, plan variants and next-step reason before/after a wrong answer. Then inspect that the generated support lesson addresses the actual misconception. A changed score alone is not adaptation.
- For exam content, verify every asserted scope item against the supplied syllabus. Generated practice is not a prediction; unsupported weights or likely questions are a defect.

## Troubleshooting

| Symptom | Check |
|---|---|
| `python` reports 3.11 or `app` import fails | Use workspace `.venv` Python 3.12 and run backend commands with current directory `backend` |
| `npm` says no `package.json` | Run `npm ci` / `npm run dev` from `frontend` |
| Port 8000 or 3000 is occupied | Inspect with `Get-NetTCPConnection -State Listen -LocalPort 8000,3000`; stop the owning process, or run API on 8001 and set frontend `BACKEND_URL` to `http://127.0.0.1:8001` before starting Next.js |
| UI says backend unavailable | Check API terminal, `BACKEND_URL`, and that API and frontend use the same `DEV_API_TOKEN` |
| Task stays `queued` | Start `python -m app.worker` from `backend` using the same `DATABASE_URL` as the API |
| Migration or database connection fails | Check `DATABASE_URL`; local SQLite must be `sqlite:///./learning.db` from `backend`. Compose's `db` hostname only works inside Compose |
| Compose cannot connect to Docker | Start Docker Desktop and wait for its engine; Docker CLI alone is not enough |
| Task fails in live mode | Read the UI error and worker log. Gemini/model config is checked before Tavily search; verify Google AI Studio credentials, model access, network, quota and API compatibility |
| Browser CORS error when calling API directly | Use the UI's same-origin `/api/backend` proxy, or set `CORS_ORIGINS` for the direct browser origin |
| Worker/API disagree after restart | Start both from `backend` with the same environment and same database URL; do not point one at `learning.db` and the other at PostgreSQL |

## Stop and Restart

For SQLite, Ctrl+C in each of the three terminals. To resume, rerun the API, worker and frontend commands above using the same `.env` files. `backend/learning.db` is persistent; migration upgrades do not reset it. Do not delete the database or run `docker compose down -v` to troubleshoot. For Compose, `docker compose down` stops containers while preserving the named database volume; run `docker compose up --build` to restart.