from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Run, Span
from ..schemas import SpanIn
from .analysis import find_root_cause


def ingest_spans(db: Session, spans: list[SpanIn]) -> int:
    """Idempotent upsert. Children usually arrive before their root, so the Run
    row is (re)derived from its spans after every batch."""
    touched = set()
    for s in spans:
        row = db.get(Span, s.span_id) or Span(id=s.span_id)
        row.run_id = s.trace_id
        row.parent_id = s.parent_span_id
        row.name, row.kind, row.status = s.name, s.kind, s.status
        row.start_ns, row.end_ns = s.start_ns, s.end_ns
        row.duration_ms = (s.end_ns - s.start_ns) / 1e6
        row.input, row.output = s.input, s.output
        row.prompt_tokens, row.completion_tokens, row.model = s.prompt_tokens, s.completion_tokens, s.model
        row.error_type, row.error_message, row.attributes = s.error_type, s.error_message, s.attributes
        if s.trace_id not in touched and db.get(Run, s.trace_id) is None:
            db.add(Run(id=s.trace_id))
            db.flush()
        db.add(row)
        touched.add(s.trace_id)
    db.flush()
    for run_id in touched:
        refresh_run(db, run_id)
    db.commit()
    return len(spans)


def refresh_run(db: Session, run_id: str) -> None:
    spans = db.scalars(select(Span).where(Span.run_id == run_id)).all()
    run = db.get(Run, run_id)
    root = next((s for s in spans if s.parent_id is None), None)

    run.span_count = len(spans)
    run.error_count = sum(s.status == "error" for s in spans)
    run.total_tokens = sum((s.prompt_tokens or 0) + (s.completion_tokens or 0) for s in spans)

    cause = find_root_cause(spans)
    run.root_cause_span_id = cause.id if cause else None
    run.error_message = (f"{cause.name}: {cause.error_message}" if cause else None)

    if root is None:
        run.status = "running"
        return
    run.name, run.input, run.output = root.name, root.input, root.output
    run.started_ns, run.ended_ns, run.duration_ms = root.start_ns, root.end_ns, root.duration_ms
    run.replay_of = (root.attributes or {}).get("agentscope.replay_of")
    # degraded = something failed but the agent recovered (e.g. a retry succeeded)
    run.status = "failed" if root.status == "error" else ("degraded" if run.error_count else "success")
