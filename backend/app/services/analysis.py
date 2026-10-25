"""Failure localisation and run-vs-run comparison."""
from __future__ import annotations

from collections import Counter
from typing import Any


def find_root_cause(spans: list) -> Any | None:
    """Earliest errored span that has no errored child = where the failure actually originated.
    (Parents like the node/run span only error because a child did.)"""
    errs = [s for s in spans if s.status == "error"]
    if not errs:
        return None
    has_err_child = {s.parent_id for s in errs if s.parent_id}
    leaves = [s for s in errs if s.id not in has_err_child]
    return min(leaves, key=lambda s: s.start_ns)


def _keyed(spans: list) -> dict[tuple[str, int], Any]:
    """Align steps across runs by (name, n-th occurrence) so retries line up correctly."""
    seen: Counter = Counter()
    out = {}
    for s in sorted(spans, key=lambda s: s.start_ns):
        out[(s.name, seen[s.name])] = s
        seen[s.name] += 1
    return out


def _tokens(s) -> int:
    return (s.prompt_tokens or 0) + (s.completion_tokens or 0) if s else 0


def compare_runs(a_spans: list, b_spans: list) -> dict:
    ka, kb = _keyed(a_spans), _keyed(b_spans)
    order = list(ka) + [k for k in kb if k not in ka]

    id_to_key = {s.id: k for k, s in ka.items()} | {s.id: k for k, s in kb.items()}
    rows, status_diff = [], {}
    for k in order:
        sa, sb = ka.get(k), kb.get(k)
        if sa is None or sb is None:
            diff = "only_in_b" if sa is None else "only_in_a"
        elif sa.status != sb.status:
            diff = "status_changed"
        else:
            diff = None
        rows.append({
            "key": f"{k[0]}#{k[1]}", "name": k[0], "occurrence": k[1],
            "kind": (sa or sb).kind,
            "a": _side(sa), "b": _side(sb),
            "diff": diff,
            "input_changed": bool(sa and sb and sa.input != sb.input),
            "output_changed": bool(sa and sb and sa.output != sb.output),
            "duration_delta_ms": round(sb.duration_ms - sa.duration_ms, 2) if sa and sb else None,
            "token_delta": _tokens(sb) - _tokens(sa),
        })
        if diff:
            status_diff[k] = (sa or sb).parent_id

    # Divergence = earliest differing step that is not merely an ancestor of another differing step.
    ancestors = set()
    for k, pid in status_diff.items():
        while pid and pid in id_to_key:
            ancestors.add(id_to_key[pid])
            p = (ka.get(id_to_key[pid]) or kb.get(id_to_key[pid]))
            pid = p.parent_id if p else None
    divergence = next((f"{k[0]}#{k[1]}" for k in order
                       if k in status_diff and k not in ancestors
                       and (ka.get(k) or kb.get(k)).kind != "run"), None)

    return {
        "divergence": divergence,
        "rows": rows,
        "summary": {
            "tokens_a": sum(map(_tokens, a_spans)), "tokens_b": sum(map(_tokens, b_spans)),
            "errors_a": sum(s.status == "error" for s in a_spans),
            "errors_b": sum(s.status == "error" for s in b_spans),
            "steps_a": len(a_spans), "steps_b": len(b_spans),
        },
    }


def _side(s) -> dict | None:
    if s is None:
        return None
    return {"span_id": s.id, "status": s.status, "duration_ms": round(s.duration_ms, 2),
            "tokens": _tokens(s), "error_message": s.error_message}
