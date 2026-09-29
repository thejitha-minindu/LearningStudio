'use client';
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

type Citation = { source_id: string; passage_id: string };
type Question = {
  id: string;
  kind: 'choice' | 'short_text';
  prompt: string;
  options: string[];
  rubric: string[];
  difficulty: string;
  citations: Citation[];
};
type Lesson = {
  lesson_id: string;
  topic_id: string;
  variant: string;
  title: string;
  objectives: string[];
  prerequisites: string[];
  estimated_minutes: number;
  sections: { heading: string; text: string; citations: Citation[] }[];
  questions: Question[];
  limitations: string[];
  practice_label: string;
  citation_validation: string;
  provenance_mode: string;
  support_audit: {
    support: string;
    explanation: string;
    disagreements: { description: string; citations: Citation[] }[];
  };
};
type Step = { action: string; reason: string; lesson_id?: string; topic_id?: string };
type Result = { score: number; confidence: number; feedback: string; method: string };
type Plan = {
  purpose: string;
  scope_status: string;
  topics: {
    id: string;
    title: string;
    objective: string;
    estimated_minutes: number;
    practice: string;
    variant: string;
    prerequisites: string[];
  }[];
  deferred: { title: string; reason: string }[];
  assumptions: string[];
  budget_minutes: number;
  remaining_minutes: number;
  planned_minutes: number;
  estimated_spent_minutes: number;
  time_note: string;
  sessions: { estimated_minutes: number; activities: { topic_id: string; minutes: number }[] }[];
};
type Progress = {
  topic_states: { topic: string; state: string; confidence: number }[];
  next_step: Step;
  mastery_policy: string;
  attempts: { attempt_id: string; lesson_id: string; question_id: string; answer: string; result: Result }[];
};
type Status = {
  status: string;
  error?: string;
  provider_mode: string;
  task: { objective: string };
  research: {
    mode?: string;
    queries?: string[];
    warnings?: string[];
    stop_reason?: string;
    missing_topics?: string[];
    coverage_method?: string;
  };
};
type Passage = { title: string; text: string; location: string; reference: string; origin: string; retrieved_at: number };
type Source = { source_id: string; reference: string; title: string; origin: string; role: string };

type PurposeMode = 'long_term' | 'exam' | 'practical';

async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const response = await fetch('/api/backend' + path, {
    method,
    headers: body && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });
  const text = await response.text();
  let data: T & { detail?: unknown };
  try {
    data = JSON.parse(text) as T & { detail?: unknown };
  } catch {
    throw new Error(
      response.ok
        ? 'Backend returned an invalid response.'
        : `Backend returned HTTP ${response.status}: ${text.slice(0, 300) || response.statusText}`
    );
  }
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  return data;
}

export default function Page() {
  const [mode, setMode] = useState('loading');
  const [goal, setGoal] = useState('');
  const [objective, setObjective] = useState('');
  const [purpose, setPurpose] = useState<PurposeMode>('long_term');
  const [total, setTotal] = useState('60');
  const [session, setSession] = useState('25');
  const [deadline, setDeadline] = useState('');
  const [prior, setPrior] = useState('');
  const [priorEvidence, setPriorEvidence] = useState('');
  const [language, setLanguage] = useState('English');
  const [depth, setDepth] = useState<'brief' | 'balanced' | 'deep'>('balanced');
  const [urls, setUrls] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [resourceRole, setResourceRole] = useState('reference');
  const [uploads, setUploads] = useState<{ kind: string; value: string; role: string }[]>([]);
  const [taskId, setTaskId] = useState('');
  const [resumeId, setResumeId] = useState('');
  const [status, setStatus] = useState<Status | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState('');
  const [passage, setPassage] = useState<Passage | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<Record<string, Result>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const submission = useRef('');
  const attemptIds = useRef<Record<string, string>>({});

  useEffect(() => {
    api<{ provider_mode: string }>('/health')
      .then(x => setMode(x.provider_mode))
      .catch(e => setError(e.message));
    const saved = localStorage.getItem('learning-task');
    if (saved) setResumeId(saved);
  }, []);

  const refresh = useCallback(async (id: string) => {
    const current = await api<Status>(`/tasks/${id}`);
    setStatus(current);
    if (current.status === 'ready' || current.status === 'failed') {
      const [newLessons, newProgress, newSources] = await Promise.all([
        api<Lesson[]>(`/tasks/${id}/lessons`),
        api<Progress>(`/tasks/${id}/progress`),
        api<Source[]>(`/tasks/${id}/sources`),
      ]);
      setLessons(newLessons);
      setProgress(newProgress);
      setSources(newSources);
      if (newLessons.length) setSelected(old => (old && newLessons.some(l => l.lesson_id === old) ? old : newLessons[0].lesson_id));
      setFeedback(Object.fromEntries(newProgress.attempts.map(a => [`${a.lesson_id}:${a.question_id}`, a.result])));
      try {
        setPlan(await api<Plan>(`/tasks/${id}/plan`));
      } catch {
        setPlan(null);
      }
    }
    return current.status;
  }, []);

  useEffect(() => {
    if (!taskId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const stage = await refresh(taskId);
        if (['ready', 'failed', 'created'].includes(stage)) return;
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [taskId, refresh, status?.status]);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function uploadFiles() {
    const refs = [...uploads];
    for (const file of files) {
      const data = new FormData();
      data.append('file', file);
      const result = await api<{ file_id: string }>('/uploads', 'POST', data);
      refs.push({ kind: 'file', value: result.file_id, role: resourceRole });
    }
    setUploads(refs);
    setFiles([]);
    return refs;
  }

  function resetForm() {
    submission.current = '';
    setGoal('');
    setObjective('');
    setPurpose('long_term');
    setTotal('60');
    setSession('25');
    setDeadline('');
    setPrior('');
    setPriorEvidence('');
    setResourceRole('reference');
    setUrls('');
    setFiles([]);
    setUploads([]);
    setError('');
    setNotice('');
  }

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!goal.trim() || goal.trim().length < 3) {
      setError('Please provide a broad or long-term goal (minimum 3 characters).');
      return;
    }
    if (!objective.trim() || objective.trim().length < 5) {
      setError('Please describe what you want to learn right now (minimum 5 characters).');
      return;
    }
    await act(async () => {
      const refs = await uploadFiles();
      const resources = [
        ...refs,
        ...urls
          .split('\n')
          .map(x => x.trim())
          .filter(Boolean)
          .map(value => ({ kind: 'url', value, role: resourceRole })),
      ];
      const id = submission.current || crypto.randomUUID();
      submission.current = id;
      await api('/tasks', 'POST', {
        task_id: id,
        learner_id: 'demo-learner',
        long_term_goal: goal.trim(),
        objective: objective.trim(),
        purpose,
        total_minutes: total ? Number(total) : null,
        session_minutes: Number(session) || 25,
        deadline: deadline ? new Date(deadline).toISOString() : null,
        prior_knowledge: prior.trim()
          ? [
              {
                topic: prior.trim(),
                state: 'developing',
                evidence: priorEvidence.trim() || 'Self-reported starting knowledge',
                evidence_type: 'self_report',
              },
            ]
          : [],
        resources,
        preferences: { language: language.trim() || 'English', depth },
      });
      await api(`/tasks/${id}/process`, 'POST');
      localStorage.setItem('learning-task', id);
      setTaskId(id);
      setPlan(null);
      setLessons([]);
      setProgress(null);
      setSelected('');
      await refresh(id);
    });
  }

  async function answer(question: Question, lesson: Lesson) {
    const key = `${lesson.lesson_id}:${question.id}`;
    await act(async () => {
      const attemptKey = `${key}:${answers[key]}`;
      const attemptId = attemptIds.current[attemptKey] || crypto.randomUUID();
      attemptIds.current[attemptKey] = attemptId;
      const result = await api<{ result: Result }>(`/tasks/${taskId}/answers`, 'POST', {
        attempt_id: attemptId,
        lesson_id: lesson.lesson_id,
        question_id: question.id,
        answer: answers[key],
      });
      setFeedback(old => ({ ...old, [key]: result.result }));
      await refresh(taskId);
    });
  }

  const active = lessons.find(l => l.lesson_id === selected);
  const inProgress = status && !['ready', 'failed', 'created'].includes(status.status);
  const cite = (citations: Citation[]) => (
    <span className="citations">
      {citations.map((c, i) => (
        <button
          key={c.passage_id}
          className="link"
          onClick={() =>
            act(async () => setPassage(await api<Passage>(`/tasks/${taskId}/passages/${c.passage_id}`)))
          }
        >
          Source {i + 1}
        </button>
      ))}
    </span>
  );

  return (
    <main>
      <header>
        <div className="eyebrow">ADAPTIVE LEARNING PLATFORM</div>
        <h1>
          Learning Studio<span>Learn with a purpose.</span>
        </h1>
        <p>
          Turn any subject or exam into a focused, evidence-backed curriculum. The system researches authoritative sources,
          budgets your study time, teaches with citations, and adapts to your quiz performance.
        </p>
        <div className="badge">
          {mode === 'fixture'
            ? 'FIXTURE MODE · Offline demonstration corpus'
            : mode === 'live'
            ? 'LIVE AI MODE · Real-time web research + Gemini generation'
            : 'Connecting to backend…'}
        </div>
        <small>Local development identity: demo-learner. This is not production authentication.</small>
      </header>

      {error && <div role="alert" className="alert error">{error}</div>}
      {notice && <div role="status" className="alert">{notice}</div>}

      <div className="workspace">
        <aside>
          <section className="card">
            <div className="row between">
              <h2>1. Set your learning context</h2>
              {(goal || objective || prior) && (
                <button type="button" className="link" onClick={resetForm} style={{ fontSize: 12 }}>
                  Reset form
                </button>
              )}
            </div>

            <form
              onSubmit={start}
              onChange={() => {
                submission.current = '';
              }}
            >
              <label>
                Broad or long-term goal
                <input
                  required
                  minLength={3}
                  maxLength={2000}
                  value={goal}
                  onChange={e => setGoal(e.target.value)}
                  placeholder="e.g. Master distributed backend systems, or Ace my computer science finals"
                />
                <div className="field-hint">The overall outcome or skill you are aiming toward.</div>
              </label>

              <label>
                What specifically do you need to learn right now?
                <textarea
                  required
                  minLength={5}
                  maxLength={2000}
                  value={objective}
                  onChange={e => setObjective(e.target.value)}
                  placeholder="e.g. Prepare for an upcoming quiz on SQL indexing, B-trees, and query optimization"
                />
                <div className="field-hint">The precise concept, chapter, or exam topic for this study session.</div>
              </label>

              <label style={{ marginBottom: 4 }}>
                Goal horizon & learning purpose
                <div className="field-hint">Choose how the AI should tailor the curriculum and questions:</div>
              </label>

              <div className="purpose-selector" role="radiogroup" aria-label="Learning purpose">
                <button
                  type="button"
                  role="radio"
                  aria-checked={purpose === 'long_term'}
                  className={`purpose-btn ${purpose === 'long_term' ? 'active' : ''}`}
                  onClick={() => setPurpose('long_term')}
                >
                  <span className="purpose-btn-icon">🧠</span>
                  <span className="purpose-btn-title">Long-Term Mastery</span>
                  <span className="purpose-btn-desc">Intuition, mechanisms & enduring mental models</span>
                </button>

                <button
                  type="button"
                  role="radio"
                  aria-checked={purpose === 'exam'}
                  className={`purpose-btn ${purpose === 'exam' ? 'active' : ''}`}
                  onClick={() => setPurpose('exam')}
                >
                  <span className="purpose-btn-icon">📝</span>
                  <span className="purpose-btn-title">Exam & Quiz Prep</span>
                  <span className="purpose-btn-desc">High-yield recall, core definitions & test practice</span>
                </button>

                <button
                  type="button"
                  role="radio"
                  aria-checked={purpose === 'practical'}
                  className={`purpose-btn ${purpose === 'practical' ? 'active' : ''}`}
                  onClick={() => setPurpose('practical')}
                >
                  <span className="purpose-btn-icon">🛠️</span>
                  <span className="purpose-btn-title">Practical Task</span>
                  <span className="purpose-btn-desc">Direct execution, commands/code & verification</span>
                </button>
              </div>

              <div className="purpose-banner">
                {purpose === 'exam' && (
                  <>
                    <strong>🎯 Exam & Quiz Prep:</strong> The AI focuses on high-yield testable topics, core definitions, active recall drills, and realistic exam-format practice checks.
                    <br />
                    <span className="muted">Upload your course syllabus or lecture slides below to anchor the scope. Without a syllabus, the scope stays provisional.</span>
                  </>
                )}
                {purpose === 'long_term' && (
                  <>
                    <strong>🧠 Long-Term Knowledge:</strong> The AI develops deep underlying mental models, foundational principles, "why it works" intuitive explanations, and cross-domain conceptual transfer for durable retention.
                  </>
                )}
                {purpose === 'practical' && (
                  <>
                    <strong>🛠️ Practical Task:</strong> The AI focuses on concrete step-by-step procedures, actionable implementation, and output verification with minimal theoretical delay.
                  </>
                )}
              </div>

              <div className="row">
                <label>
                  Total study budget (minutes)
                  <input
                    type="number"
                    min="1"
                    max="100000"
                    value={total}
                    onChange={e => setTotal(e.target.value)}
                    placeholder="e.g. 60"
                  />
                  <div className="field-hint">Leave blank for automatic budget.</div>
                </label>
                <label>
                  Session length (minutes)
                  <input
                    type="number"
                    required
                    min="1"
                    max="240"
                    value={session}
                    onChange={e => setSession(e.target.value)}
                  />
                  <div className="field-hint">Pomodoro session chunk.</div>
                </label>
              </div>

              <label>
                Target deadline (optional)
                <input
                  type="datetime-local"
                  value={deadline}
                  onChange={e => setDeadline(e.target.value)}
                />
                <div className="field-hint">Limits your study plan to the remaining time before your test.</div>
              </label>

              <details>
                <summary>Prior knowledge (optional) — skip what you already know</summary>
                <label>
                  Topics you already know
                  <input
                    value={prior}
                    onChange={e => setPrior(e.target.value)}
                    maxLength={150}
                    placeholder="e.g. Python syntax, basic SQL queries, linear algebra basics"
                  />
                  <div className="field-hint">The AI will build upon these rather than re-explaining them.</div>
                </label>
                {prior && (
                  <label>
                    Evidence / what you can do
                    <textarea
                      value={priorEvidence}
                      onChange={e => setPriorEvidence(e.target.value)}
                      maxLength={2000}
                      placeholder="e.g. Self-report: I can write loops, functions and basic SELECT/JOIN queries"
                    />
                  </label>
                )}
              </details>

              <div className="row">
                <label>
                  Language
                  <input
                    value={language}
                    onChange={e => setLanguage(e.target.value)}
                    required
                    maxLength={40}
                  />
                </label>
                <label>
                  Explanation depth
                  <select
                    value={depth}
                    onChange={e => setDepth(e.target.value as 'brief' | 'balanced' | 'deep')}
                  >
                    <option value="brief">Brief (Concise summaries)</option>
                    <option value="balanced">Balanced (Recommended)</option>
                    <option value="deep">Deep (Comprehensive dive)</option>
                  </select>
                </label>
              </div>

              <details>
                <summary>Optional study materials — syllabus, PDFs, or URLs</summary>
                <div className="field-hint" style={{ marginBottom: 12 }}>
                  Upload a course syllabus to define exam scope, or lecture slides to provide exact source passages. You can also start without files — the AI will research automatically.
                </div>
                <label>
                  Role for URLs / next upload
                  <select
                    value={resourceRole}
                    onChange={e => setResourceRole(e.target.value)}
                  >
                    <option value="reference">Reference material</option>
                    <option value="syllabus">Syllabus / exam scope</option>
                    <option value="lecture">Lecture material / notes</option>
                  </select>
                </label>
                <label>
                  Public URLs, one per line
                  <textarea
                    value={urls}
                    onChange={e => setUrls(e.target.value)}
                    placeholder="https://docs.python.org/3/tutorial/..."
                  />
                </label>
                <label>
                  PDF, TXT or HTML · up to 5 MB each
                  <input
                    type="file"
                    accept=".pdf,.txt,.html,.htm"
                    multiple
                    onChange={e => setFiles(Array.from(e.target.files || []))}
                  />
                </label>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || !files.length}
                  onClick={() =>
                    act(async () => {
                      await uploadFiles();
                      setNotice('Resources uploaded. You can choose a different role for another batch if desired.');
                    })
                  }
                >
                  Upload selected files
                </button>
                {uploads.map((r, i) => (
                  <p key={r.value}>
                    {i + 1}. Uploaded {r.role}{' '}
                    <button
                      type="button"
                      className="link"
                      onClick={() => setUploads(uploads.filter(x => x !== r))}
                    >
                      Remove
                    </button>
                  </p>
                ))}
                {purpose === 'exam' && (
                  <p className="warning" style={{ fontSize: 13, marginTop: 10 }}>
                    💡 For exam preparation, uploading a syllabus locks down the course scope. Without a syllabus, exam scope remains provisional.
                  </p>
                )}
              </details>

              {mode === 'fixture' && (
                <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                  Currently running in <strong>fixture mode</strong> (offline demo corpus). Live AI research and lesson generation on ANY custom topic is enabled by configuring <code>PROVIDER_MODE=live</code> with a <code>GEMINI_API_KEY</code> in <code>.env</code>.
                </p>
              )}

              <button
                disabled={busy || !!inProgress || !goal.trim() || !objective.trim()}
                type="submit"
                style={{ marginTop: 16 }}
              >
                {busy
                  ? 'Working…'
                  : inProgress
                  ? 'Processing in background…'
                  : !goal.trim() || !objective.trim()
                  ? 'Fill in goal and objective above'
                  : '✨ Create Learning Task'}
              </button>
            </form>
          </section>

          <section className="card">
            <h2>Resume a task</h2>
            <label>
              Task ID
              <input
                value={resumeId}
                onChange={e => setResumeId(e.target.value)}
                placeholder="task-..."
              />
            </label>
            <button
              className="secondary"
              disabled={busy || !resumeId.trim()}
              onClick={() =>
                act(async () => {
                  await refresh(resumeId.trim());
                  setTaskId(resumeId.trim());
                  setSelected('');
                  localStorage.setItem('learning-task', resumeId.trim());
                })
              }
            >
              Open saved task
            </button>
          </section>
        </aside>

        <div className="learning">
          {!taskId && (
            <section className="card empty">
              <div className="eyebrow">NO DOCUMENTS REQUIRED</div>
              <h2>Start with what you want to learn.</h2>
              <p>The module finds evidence, builds a plan around your time, and adjusts dynamically based on your quiz and exercise answers.</p>
              <ol>
                <li><strong>Research & Outline:</strong> Identifies core foundations and key concepts.</li>
                <li><strong>Evidence-Backed Lessons:</strong> Study with inspectable, cited source passages.</li>
                <li><strong>Active Practice:</strong> Practice with choice and short-answer questions.</li>
                <li><strong>Adaptive Feedback:</strong> System detects gaps and generates focused support lessons.</li>
              </ol>
            </section>
          )}

          {taskId && status && (
            <section className="card">
              <div className="row between">
                <h2>2. Research & plan</h2>
                <span className={`badge ${status.status === 'failed' ? 'danger' : ''}`}>
                  {status.status}
                </span>
              </div>
              <p>{status.task.objective}</p>
              <small className="muted">Task ID: {taskId}</small>

              {inProgress && (
                <p role="status">Processing in the background worker. This page updates automatically.</p>
              )}
              {status.error && (
                <div className="alert error">
                  <p>{status.error}</p>
                  <button
                    disabled={busy}
                    onClick={() =>
                      act(async () => {
                        await api(`/tasks/${taskId}/process`, 'POST');
                        await refresh(taskId);
                      })
                    }
                  >
                    Retry processing
                  </button>
                </div>
              )}

              <details>
                <summary>Research report & sources</summary>
                <p>
                  {status.research.mode === 'fixture'
                    ? 'Fixture resource acquisition — no public web search was performed.'
                    : 'Live research is bounded by configured search and page limits.'}
                </p>
                <p>Stop reason: {status.research.stop_reason || 'Pending'}</p>
                <p>{status.research.coverage_method}</p>
                {status.research.queries?.map(q => (
                  <p key={q}>
                    <strong>Query:</strong> {q}
                  </p>
                ))}
                {status.research.warnings?.map((w, i) => (
                  <p className="warning" key={i}>
                    {w}
                  </p>
                ))}
                {sources.map(s => (
                  <p key={s.source_id}>
                    <strong>{s.title}</strong> · {s.origin} / {s.role}
                    <br />
                    {s.reference.startsWith('http') ? (
                      <a href={s.reference} target="_blank" rel="noreferrer">
                        Open original source
                      </a>
                    ) : (
                      <small>{s.reference}</small>
                    )}
                  </p>
                ))}
              </details>

              {plan && (
                <>
                  <div className="metrics">
                    <div>
                      <b>{plan.budget_minutes}m</b>effective budget
                    </div>
                    <div>
                      <b>{plan.planned_minutes}m</b>planned remaining
                    </div>
                    <div>
                      <b>{plan.estimated_spent_minutes}m</b>estimated used
                    </div>
                  </div>
                  <p className={plan.scope_status === 'provisional' ? 'warning' : 'muted'}>
                    Scope: {plan.scope_status.replaceAll('_', ' ')}
                  </p>
                  {plan.assumptions.map((a, i) => (
                    <p className="muted" key={i}>
                      {a}
                    </p>
                  ))}
                  <ol className="plan">
                    {plan.topics.map(t => (
                      <li key={t.id + t.variant}>
                        <strong>{t.title}</strong> · ≈{t.estimated_minutes} min{' '}
                        {t.variant === 'support' && '· focused support'}
                        <p>{t.objective}</p>
                        <small>
                          Prerequisites: {t.prerequisites.join(', ') || 'none'} · Practice: {t.practice}
                        </small>
                      </li>
                    ))}
                  </ol>
                  {plan.deferred.length > 0 && (
                    <details open>
                      <summary>Deferred content</summary>
                      {plan.deferred.map((d, i) => (
                        <p key={i}>
                          <strong>{d.title}:</strong> {d.reason}
                        </p>
                      ))}
                    </details>
                  )}
                  <details>
                    <summary>Suggested study sessions & budget adjustment</summary>
                    {plan.sessions.map((s, i) => (
                      <p key={i}>
                        Session {i + 1} · ≈{s.estimated_minutes} minutes ·{' '}
                        {s.activities.map(a => a.topic_id).join(', ')}
                      </p>
                    ))}
                    <p className="muted">{plan.time_note}</p>
                    <div className="row">
                      <label>
                        Revised total minutes
                        <input
                          type="number"
                          min="1"
                          value={total}
                          onChange={e => setTotal(e.target.value)}
                        />
                      </label>
                      <label>
                        Session minutes
                        <input
                          type="number"
                          min="1"
                          max="240"
                          value={session}
                          onChange={e => setSession(e.target.value)}
                        />
                      </label>
                    </div>
                    <button
                      className="secondary"
                      disabled={busy || !!inProgress || !total}
                      onClick={() =>
                        act(async () => {
                          await api(`/tasks/${taskId}/time`, 'PATCH', {
                            total_minutes: Number(total),
                            session_minutes: Number(session),
                          });
                          await refresh(taskId);
                        })
                      }
                    >
                      Recalculate remaining work
                    </button>
                  </details>
                </>
              )}
            </section>
          )}

          {lessons.length > 0 && (
            <section className="card">
              <h2>3. Study & practise</h2>
              <nav aria-label="Lessons" className="tabs">
                {lessons.map(l => (
                  <button
                    key={l.lesson_id}
                    className={l.lesson_id === selected ? '' : 'secondary'}
                    onClick={() => setSelected(l.lesson_id)}
                  >
                    {l.title}
                  </button>
                ))}
              </nav>

              {active && (
                <article>
                  <div className="eyebrow">
                    {active.provenance_mode.toUpperCase()} LESSON · ≈{active.estimated_minutes} MINUTES
                  </div>
                  <h2>{active.title}</h2>
                  <ul>
                    {active.objectives.map(o => (
                      <li key={o}>{o}</li>
                    ))}
                  </ul>
                  <p className="muted">
                    Essential prerequisites: {active.prerequisites.join(', ') || 'No additional prerequisites'}
                  </p>
                  {active.sections.map((s, i) => (
                    <section key={i} className="lesson-section">
                      <h3>{s.heading}</h3>
                      <p className="prose">{s.text}</p>
                      {cite(s.citations)}
                    </section>
                  ))}

                  <div className="alert">
                    <strong>Evidence check: {active.support_audit.support}</strong>
                    <p>{active.support_audit.explanation}</p>
                    <small>{active.citation_validation}</small>
                    {active.support_audit.disagreements.map((d, i) => (
                      <p key={i} className="warning">
                        Disagreement: {d.description} {cite(d.citations)}
                      </p>
                    ))}
                  </div>

                  {active.limitations.map((l, i) => (
                    <p key={i} className="muted">{l}</p>
                  ))}

                  <h3>Understanding check</h3>
                  <p className="muted">
                    {active.practice_label}. These checks assess mastery and identify any gaps in your understanding.
                  </p>
                  {active.questions.map(q => {
                    const key = `${active.lesson_id}:${q.id}`;
                    return (
                      <form
                        key={key}
                        className="question"
                        onSubmit={e => {
                          e.preventDefault();
                          void answer(q, active);
                        }}
                      >
                        <fieldset>
                          <legend>{q.prompt}</legend>
                          <small>
                            {q.difficulty} ·{' '}
                            {q.kind === 'short_text'
                              ? 'Rubric-based assessment feedback'
                              : 'Deterministic check'}
                          </small>
                          {q.kind === 'choice' ? (
                            q.options.map(option => (
                              <label className="option" key={option}>
                                <input
                                  type="radio"
                                  name={key}
                                  value={option}
                                  checked={answers[key] === option}
                                  onChange={() => setAnswers(old => ({ ...old, [key]: option }))}
                                  required
                                />
                                {option}
                              </label>
                            ))
                          ) : (
                            <label>
                              Your reasoning
                              <textarea
                                required
                                maxLength={4000}
                                value={answers[key] || ''}
                                onChange={e => setAnswers(old => ({ ...old, [key]: e.target.value }))}
                                placeholder="Explain your answer and intermediate steps..."
                              />
                            </label>
                          )}
                          <details>
                            <summary>Assessment rubric</summary>
                            <ul>
                              {q.rubric.map(r => (
                                <li key={r}>{r}</li>
                              ))}
                            </ul>
                          </details>
                          <button disabled={busy || !!inProgress || !answers[key]} type="submit">
                            Check answer
                          </button>
                          {feedback[key] && (
                            <div className="feedback" role="status">
                              <strong>
                                {Math.round(feedback[key].score * 100)}% · confidence{' '}
                                {Math.round(feedback[key].confidence * 100)}%
                              </strong>
                              <p>{feedback[key].feedback}</p>
                              <small>Method: {feedback[key].method}</small>
                            </div>
                          )}
                        </fieldset>
                      </form>
                    );
                  })}
                </article>
              )}
            </section>
          )}

          {progress && (
            <section className="card">
              <h2>4. Progress & next step</h2>
              <p>{progress.next_step.reason}</p>
              <button
                disabled={
                  busy ||
                  !!inProgress ||
                  ['complete', 'review_budget', 'process'].includes(progress.next_step.action)
                }
                onClick={() =>
                  act(async () => {
                    const step = await api<Step>(`/tasks/${taskId}/next`, 'POST');
                    if (step.lesson_id) setSelected(step.lesson_id);
                    setNotice(step.reason);
                    await refresh(taskId);
                  })
                }
              >
                {progress.next_step.action === 'support'
                  ? 'Create focused support lesson'
                  : progress.next_step.action === 'generate'
                  ? 'Create next lesson'
                  : 'Open recommended lesson'}
              </button>
              <div className="states">
                {progress.topic_states.map(s => (
                  <div key={s.topic}>
                    <strong>{s.topic}</strong>
                    <span>
                      {s.state.replaceAll('_', ' ')} · {Math.round(s.confidence * 100)}% confidence
                    </span>
                  </div>
                ))}
              </div>
              <p className="muted">{progress.mastery_policy}</p>
            </section>
          )}
        </div>
      </div>

      {passage && (
        <div className="overlay" onClick={() => setPassage(null)}>
          <section
            className="card source-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Stored source passage"
            onClick={e => e.stopPropagation()}
          >
            <button className="secondary close" autoFocus onClick={() => setPassage(null)}>
              Close
            </button>
            <div className="eyebrow">ACTUAL STORED EVIDENCE · {passage.origin.toUpperCase()}</div>
            <h2>{passage.title}</h2>
            <p className="muted">
              {passage.location} · retrieved {new Date(passage.retrieved_at * 1000).toLocaleString()}
            </p>
            <blockquote>{passage.text}</blockquote>
            {passage.reference.startsWith('http') ? (
              <a href={passage.reference} target="_blank" rel="noreferrer">
                Open original source
              </a>
            ) : (
              <p className="muted">Reference: {passage.reference}</p>
            )}
          </section>
        </div>
      )}

      <footer>Learning Studio · Local prototype · Calendar events and reminders belong to the coordinating system.</footer>
    </main>
  );
}
