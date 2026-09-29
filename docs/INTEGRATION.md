# Coordinator boundary

The coordinator decides **what and why** the learner should learn and supplies only authorized
resource locations. This module returns a learning plan, evidence-supported lessons, assessment
feedback and recommended learning actions. The coordinator continues to own calendar events,
reminders, activity collection, and high-level goal management.

Base URL: `http://localhost:8000`. Interactive contracts: `/docs`; JSON schema: `/openapi.json`.
All data endpoints require `X-Dev-Token` and `X-Learner-ID` in this local prototype.

## Task request

```json
{
  "task_id": "neural-demo-001",
  "learner_id": "demo-learner",
  "long_term_goal": "Build machine learning applications",
  "objective": "Learn neural networks with Python",
  "purpose": "long_term",
  "deadline": null,
  "total_minutes": 60,
  "session_minutes": 25,
  "prior_knowledge": [
    {"topic": "Python basics", "state": "developing", "evidence_type": "self_report", "evidence": "Can write loops and functions"}
  ],
  "resources": [],
  "preferences": {"language": "English", "depth": "balanced"}
}
```

`purpose` is `long_term`, `exam`, or `practical`; documents never choose it. `deadline` is an
ISO timestamp **with timezone** or null. `total_minutes` may be null; a provisional budget of
three sessions is then disclosed. An empty `prior_knowledge` list is valid and does not imply
understanding. Knowledge values are `unknown`, `needs_support`, `developing`, `demonstrated`;
input evidence types are `self_report`, `diagnostic`, `exercise`. These input values are claims;
the module's own assessment history determines demonstrated state conservatively.

Each resource has `kind` (`url`, `file`, `local`), `value`, and optional `role` (`reference`,
`syllabus`, `lecture`). URLs must be public HTTP(S). File values are IDs returned by `/uploads`
for the same identity. `local` is optional development functionality bounded by
`ALLOWED_RESOURCE_DIR` **inside the backend host/container**. A path on another service cannot
be read automatically. Uploaded resource contents remain untrusted data.

Full example requests: `examples/neural-networks.json` and `examples/database-exam.json`.
Replace the latter's file-ID placeholders after uploading its supplied materials.

## Operations

| Method | Path | Result |
| --- | --- | --- |
| POST | `/uploads` | Multipart field `file`; returns `file_id`, name and byte count |
| POST | `/tasks` | Validates and persists task; returns ID/status (201) |
| GET | `/tasks/{id}` | Input, stage, job attempts, research report, actionable error |
| POST | `/tasks/{id}/resources` | Adds one authorized resource before planning |
| POST | `/tasks/{id}/process` | Enqueues processing or retries the failed job (202) |
| GET | `/tasks/{id}/plan` | Topics, objectives, prerequisites, practice, sources, estimates, deferred work |
| GET | `/tasks/{id}/lessons` | Generated lessons and public questions; answer keys are omitted |
| GET | `/tasks/{id}/sources` | Source metadata including origin and supplied reference |
| GET | `/tasks/{id}/passages/{passage_id}` | Exact stored passage, location and source metadata |
| POST | `/tasks/{id}/answers` | Grades and persists one attempt; returns state and next action |
| GET | `/tasks/{id}/progress` | Learner topic evidence, task attempts, next step |
| POST | `/tasks/{id}/next` | Returns existing lesson or enqueues recommended lesson/support (202) |
| PATCH | `/tasks/{id}/time` | Recalculates uncompleted work from revised total/session minutes |

No webhook or scheduling side effect is implemented. Poll task status (roughly every 3 seconds)
until `ready` or `failed`; stages include `created`, `queued`, `researching`, `planning`, and
`generating`. Stop polling terminal statuses. `ready` can include deferred topics or zero fitting
lessons; inspect the plan and research limitations, not just the status string.

Recommended actions: `process`, `study`, `generate`, `support`, `review_budget`, `complete`.
`complete` means the planned checks are done, **not** that the learner has mastered the objective.
An inadequate budget returns deferred work and may require a time update before `/next`.
Resource changes after a plan exists require a new task ID to preserve old evidence and attempts.

## CLI example

The following commands use POSIX shell syntax; the Python demo works on Windows too.

```sh
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-Token: local-development-only' -H 'X-Learner-ID: demo-learner' \
  --data-binary @examples/neural-networks.json

curl -X POST http://localhost:8000/tasks/neural-demo-001/process \
  -H 'X-Dev-Token: local-development-only' -H 'X-Learner-ID: demo-learner'

curl http://localhost:8000/tasks/neural-demo-001 \
  -H 'X-Dev-Token: local-development-only' -H 'X-Learner-ID: demo-learner'
```

An answer request:

```json
{
  "attempt_id": "unique-coordinator-attempt-001",
  "lesson_id": "ID_FROM_LESSON_RESPONSE",
  "question_id": "check",
  "answer": "-1"
}
```

Choice answers must equal one of the options exactly. Free-text answers are graded against
the stored rubric with a separate confidence value. Fixture keyword checks explicitly report
`fixture_keyword_demo`; live rubric grading reports `model_rubric`. Deterministic choices
report `deterministic`. Feedback is formative, not an exam certification.

A time update is `{"total_minutes":90,"session_minutes":20}`. Total means the revised total
including already attempted lessons' estimates, not an additional allocation. Replanning
never deletes earlier lessons or their evidence. Already-generated lessons remain inspectable.

## Idempotency, failures, and provenance

Reuse `task_id` with the identical original request to safely retrieve the existing result.
A conflicting payload returns 409. Uploads deduplicate bytes per learner. Repeated `/process`
calls do not create duplicate active jobs. Use the same `attempt_id` when retrying delivery;
changing that attempt's answer returns 409. An intentional new try gets a new attempt ID,
but repeated questions do not count as independent evidence of mastery.

Validation errors are 422; unsupported upload types 415; oversized bodies 413; ownership
violations generally 404; bad tokens 401; state conflicts 409; rate limits 429; synchronous
grading-provider failures 503. Long-running failures are stored as `status=failed` with a
sanitized, actionable `error`. Provider failure response bodies and documents are not logged.

Source metadata stores the source URL or authorized file reference, title, retrieval timestamp,
role and origin (`supplied`, `web`, `fixture`). A passage preserves page/section and character
location. Every lesson explanation/example and question contains `source_id`/`passage_id`
pairs which must resolve within that task. Search snippets never enter the passage store.
`support_audit` reports the separate, fallible semantic check and cited disagreements.
Fixture mode says this check was not performed. A valid ID is never labelled factual proof.
