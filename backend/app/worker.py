"""Persistent, leased SQL jobs. Run separately: python -m app.worker."""
import logging
import threading
import time
from sqlalchemy import or_, select, update
from .config import settings
from .db import Job, Plan, Session, Task, now, uid
from .learning import build_plan, generate_lesson, make_curriculum, seed_knowledge
from .providers import ProviderError, providers
from .research import Research
from .safety import ResourceError

logger = logging.getLogger('learning.worker')


def claim(factory=Session):
    with factory.begin() as db:
        candidate = db.scalar(select(Job).where(or_(Job.status == 'queued', (Job.status == 'running') & (Job.lease_until < now()))).order_by(Job.task_id).with_for_update(skip_locked=True))
        if not candidate:
            return None
        if candidate.attempts >= settings().job_max_attempts:
            candidate.status = 'failed'
            task = db.get(Task, candidate.task_id)
            task.status, task.error = 'failed', 'Worker retry limit reached. Check worker health; explicitly retry processing.'
            return None
        token = uid()
        changed = db.execute(update(Job).where(Job.task_id == candidate.task_id, or_(Job.status == 'queued', (Job.status == 'running') & (Job.lease_until < now()))).values(status='running', token=token, lease_until=now() + 120, attempts=Job.attempts + 1))
        return (candidate.task_id, token) if changed.rowcount == 1 else None


def heartbeat(task_id, token, stop, factory):
    while not stop.wait(20):
        try:
            with factory.begin() as db:
                db.execute(update(Job).where(Job.task_id == task_id, Job.token == token, Job.status == 'running').values(lease_until=now() + 120))
        except Exception:
            logger.warning('Lease heartbeat failed for task %s', task_id)


def process(task_id, token, factory=Session, config=None):
    config = config or settings()
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(task_id, token, stop, factory), daemon=True)
    thread.start()
    try:
        with factory() as db:
            task, job = db.get(Task, task_id), db.get(Job, task_id)

            def save(stage=None):
                # Fence a worker whose lease was claimed by another process.
                current_token = db.scalar(select(Job.token).where(Job.task_id == task_id))
                if current_token != token:
                    raise ProviderError('Worker lease changed; stale work was discarded.')
                if stage:
                    task.status = stage
                db.commit()

            search, generator = providers(config)
            task.error = None
            seed_knowledge(db, task)
            model_desc = config.ollama_model if getattr(config, 'generator_provider', '') == 'ollama' else config.gemini_model
            logger.info('Claimed task %s (kind=%s, provider=%s, model=%s)', task_id, job.kind, getattr(config, 'generator_provider', 'gemini'), model_desc)
            if job.kind == 'pipeline':
                save('researching')
                research = Research(db, task, config, search)
                research.supplied()
                logger.info('Task %s: Generating curriculum...', task_id)
                curriculum = make_curriculum(db, task, generator)
                logger.info('Task %s: Searching and gathering topic evidence...', task_id)
                report = research.run(curriculum['topics'])
                task.report = report
                save('planning')
                logger.info('Task %s: Building study plan...', task_id)
                plan_data = build_plan(db, task, curriculum, report)
                plan = db.get(Plan, task_id)
                if plan:
                    plan.data = plan_data
                else:
                    plan = Plan(task_id=task_id, data=plan_data)
                    db.add(plan)
                save('generating')
                if plan_data['topics']:
                    logger.info('Task %s: Generating lesson content and semantic audit...', task_id)
                    generate_lesson(db, task, plan_data['topics'][0], generator)
                elif report['missing_topics'] and not report['pages_attempted']:
                    raise ProviderError('No usable evidence found. Supply accessible sources or refine the objective and retry.')
            else:
                save('generating')
                plan = db.get(Plan, task_id)
                variant = 'support' if job.kind == 'support' else 'standard'
                entry = next((t for t in plan.data['topics'] if t['id'] == job.topic_id and t['variant'] == variant), None)
                if not entry:
                    raise ProviderError('The next lesson does not fit the current plan. Update the study budget.')
                logger.info('Task %s: Generating lesson variant %s...', task_id, variant)
                generate_lesson(db, task, entry, generator)
            job.status, job.lease_until = 'done', 0
            save('ready')
            logger.info('Completed task %s successfully (%s mode)', task_id, config.provider_mode)
    except Exception as error:
        # Never log prompts, documents, provider payloads, URLs or exception strings from third parties.
        message = str(error) if isinstance(error, (ProviderError, ResourceError)) else 'Processing failed unexpectedly. Check worker configuration and database availability, then retry.'
        with factory.begin() as db:
            job = db.get(Job, task_id)
            if job and job.token == token:
                job.status, job.lease_until = 'failed', 0
                task = db.get(Task, task_id)
                task.status, task.error = 'failed', message
        logger.error('Task %s failed: %s (%s)', task_id, message, type(error).__name__)
    finally:
        stop.set()
        thread.join(timeout=1)


def run_once(factory=Session, config=None):
    item = claim(factory)
    if not item:
        return False
    process(*item, factory=factory, config=config)
    return True


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    logger.info('Background worker started. Listening for tasks (provider_mode=%s)...', settings().provider_mode)
    while True:
        if not run_once():
            time.sleep(1)
