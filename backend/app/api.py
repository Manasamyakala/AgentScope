import copy
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Run, Span
from .replay import WORKFLOWS
from .schemas import IngestIn, ReplayIn
from .services.analysis import compare_runs
from .services.ingest import ingest_spans

router = APIRouter(prefix="/api")


def _run_out(r: Run) -> dict:
    return {
        "id": r.id, "name": r.name, "status": r.status, "duration_ms": r.duration_ms,
        "total_tokens": r.total_tokens, "span_count": r.span_count, "error_count": r.error_count,
        "replay_of": r.replay_of, "error_message": r.error_message,
        "started_ns": r.started_ns, "input": r.input, "output": r.output,
        "root_cause_span_id": r.root_cause_span_id,
    }


def _span_out(s: Span, t0: int) -> dict:
    return {
        "id": s.id, "parent_id": s.parent_id, "name": s.name, "kind": s.kind, "status": s.status,
        "offset_ms": round((s.start_ns - t0) / 1e6, 2), "duration_ms": round(s.duration_ms, 2),
        "input": s.input, "output": s.output, "model": s.model,
        "prompt_tokens": s.prompt_tokens, "completion_tokens": s.completion_tokens,
        "error_type": s.error_type, "error_message": s.error_message, "attributes": s.attributes,
    }


def _spans(db: Session, run_id: str) -> list[Span]:
    spans = db.scalars(select(Span).where(Span.run_id == run_id).order_by(Span.start_ns)).all()
    if not spans:
        raise HTTPException(404, f"run {run_id} not found")
    return list(spans)


@router.post("/ingest/spans")
def ingest(body: IngestIn, db: Session = Depends(get_db)):
    return {"ingested": ingest_spans(db, body.spans)}


@router.get("/runs")
def list_runs(status: str | None = None, name: str | None = None,
              limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    q = select(Run).order_by(Run.started_ns.desc().nullslast())
    if status:
        q = q.where(Run.status == status)
    if name:
        q = q.where(Run.name == name)
    return [_run_out(r) for r in db.scalars(q.limit(limit))]


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    spans = _spans(db, run_id)
    t0 = min(s.start_ns for s in spans)
    return {"run": _run_out(run), "spans": [_span_out(s, t0) for s in spans]}


@router.get("/runs/{run_id}/compare/{other_id}")
def compare(run_id: str, other_id: str, db: Session = Depends(get_db)):
    """A = run_id (usually the failed one), B = other_id (usually the successful one)."""
    return {
        "a": _run_out(db.get(Run, run_id)), "b": _run_out(db.get(Run, other_id)),
        **compare_runs(_spans(db, run_id), _spans(db, other_id)),
    }


@router.post("/runs/{run_id}/replay")
def replay(run_id: str, body: ReplayIn, db: Session = Depends(get_db)):
    """Re-execute the same workflow with the same input (plus optional config overrides)
    and link the new run back to the original, ready to compare."""
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    fn = WORKFLOWS.get(run.name)
    if not fn:
        raise HTTPException(422, f"no replayable workflow registered for '{run.name}'")
    inp = copy.deepcopy(run.input or {})
    inp.setdefault("config", {}).update(body.config_overrides)
    new_id = fn(inp, replay_of=run_id)
    return {"run_id": new_id, "replay_of": run_id}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    runs = db.scalars(select(Run)).all()
    by_step = defaultdict(lambda: {"calls": 0, "errors": 0, "total_ms": 0.0, "tokens": 0})
    for s in db.scalars(select(Span)):
        d = by_step[s.name]
        d["calls"] += 1
        d["errors"] += s.status == "error"
        d["total_ms"] += s.duration_ms
        d["tokens"] += (s.prompt_tokens or 0) + (s.completion_tokens or 0)
    return {
        "runs_by_status": {st: sum(r.status == st for r in runs)
                           for st in ("success", "degraded", "failed", "running")},
        "total_tokens": sum(r.total_tokens for r in runs),
        "steps": sorted(
            [{"name": n, "calls": d["calls"], "errors": d["errors"],
              "error_rate": round(d["errors"] / d["calls"], 3),
              "avg_ms": round(d["total_ms"] / d["calls"], 2), "tokens": d["tokens"]}
             for n, d in by_step.items()],
            key=lambda x: -x["error_rate"]),
    }
