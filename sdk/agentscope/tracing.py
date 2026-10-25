"""AgentScope tracing SDK.

Built on OpenTelemetry: every agent step is a real OTel span. A custom
SpanExporter converts finished spans into AgentScope's JSON shape and hands
them to a "sink" (HTTP POST to the server by default, or any callable).
One OTel trace == one AgentScope run.
"""
from __future__ import annotations

import functools
import inspect
import json
import logging
import os
import urllib.request
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Sequence

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import StatusCode

log = logging.getLogger("agentscope")
_provider: TracerProvider | None = None
_tracer = None
MAX_PAYLOAD_CHARS = 20_000


def _dump(value: Any) -> str:
    """JSON-serialise anything; oversized payloads are truncated safely."""
    text = json.dumps(value, default=repr)
    if len(text) > MAX_PAYLOAD_CHARS:
        text = json.dumps({"_truncated": text[:MAX_PAYLOAD_CHARS]})
    return text


# ----------------------------------------------------------------- exporter
def _convert(s: ReadableSpan) -> dict:
    a = dict(s.attributes or {})

    def pop_json(key):
        v = a.pop(key, None)
        return json.loads(v) if isinstance(v, str) else v

    is_err = s.status.status_code == StatusCode.ERROR
    return {
        "trace_id": f"{s.context.trace_id:032x}",
        "span_id": f"{s.context.span_id:016x}",
        "parent_span_id": f"{s.parent.span_id:016x}" if s.parent else None,
        "name": s.name,
        "kind": a.pop("as.kind", "step"),
        "status": "error" if is_err else "ok",
        "start_ns": s.start_time,
        "end_ns": s.end_time,
        "input": pop_json("as.input"),
        "output": pop_json("as.output"),
        "prompt_tokens": int(a.pop("as.prompt_tokens", 0)),
        "completion_tokens": int(a.pop("as.completion_tokens", 0)),
        "model": a.pop("as.model", None),
        "error_type": a.pop("as.error_type", None),
        "error_message": (s.status.description or None) if is_err else None,
        "attributes": a,
    }


class AgentScopeExporter(SpanExporter):
    def __init__(self, sink: Callable[[list[dict]], None]):
        self._sink = sink

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            self._sink([_convert(s) for s in spans])
            return SpanExportResult.SUCCESS
        except Exception:  # never let observability break the agent
            log.exception("AgentScope export failed")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


def http_sink(endpoint: str) -> Callable[[list[dict]], None]:
    url = endpoint.rstrip("/") + "/api/ingest/spans"

    def send(batch: list[dict]) -> None:
        req = urllib.request.Request(
            url,
            data=json.dumps({"spans": batch}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5).read()

    return send


def init(service_name="agent", endpoint: str | None = None,
         sink: Callable[[list[dict]], None] | None = None, sync: bool = False):
    """Call once at startup. sync=True exports every span immediately."""
    global _provider, _tracer
    sink = sink or http_sink(endpoint or os.getenv("AGENTSCOPE_ENDPOINT", "http://localhost:8000"))
    _provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    processor_cls = SimpleSpanProcessor if sync else BatchSpanProcessor
    _provider.add_span_processor(processor_cls(AgentScopeExporter(sink)))
    _tracer = _provider.get_tracer("agentscope")


def flush() -> None:
    if _provider:
        _provider.force_flush()


# ------------------------------------------------------------------ helpers
class Step:
    """Handle yielded by span()/run() so code can attach data to the live span."""

    def __init__(self, otel_span):
        self._s = otel_span

    @property
    def trace_id(self) -> str:
        return f"{self._s.get_span_context().trace_id:032x}"

    def set_input(self, v): self._s.set_attribute("as.input", _dump(v))
    def set_output(self, v): self._s.set_attribute("as.output", _dump(v))
    def set_attr(self, k, v): self._s.set_attribute(k, v)

    def set_llm(self, model: str, prompt_tokens: int, completion_tokens: int):
        self._s.set_attribute("as.model", model)
        self._s.set_attribute("as.prompt_tokens", prompt_tokens)
        self._s.set_attribute("as.completion_tokens", completion_tokens)


@contextmanager
def span(name: str, kind: str = "step", input: Any = None) -> Iterator[Step]:
    """kind: run | node | llm | tool | api | reasoning | step"""
    if _tracer is None:
        raise RuntimeError("Call agentscope.init() before tracing.")
    with _tracer.start_as_current_span(name) as s:
        s.set_attribute("as.kind", kind)
        st = Step(s)
        if input is not None:
            st.set_input(input)
        try:
            yield st
        except Exception as e:
            s.set_attribute("as.error_type", type(e).__name__)
            raise  # OTel records the exception + ERROR status on the way out


@contextmanager
def run(name: str, input: Any = None, replay_of: str | None = None) -> Iterator[Step]:
    """Root span of one agent execution."""
    with span(name, kind="run", input=input) as st:
        if replay_of:
            st.set_attr("agentscope.replay_of", replay_of)
        yield st


def traced(name: str | None = None, kind: str = "tool"):
    """Decorator: wrap a function (sync or async) in a span, capturing args and result."""

    def deco(fn):
        span_name = name or fn.__name__
        sig = inspect.signature(fn)

        def capture(args, kwargs):
            try:
                return dict(sig.bind_partial(*args, **kwargs).arguments)
            except TypeError:
                return {"args": args, "kwargs": kwargs}

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                with span(span_name, kind, capture(args, kwargs)) as st:
                    out = await fn(*args, **kwargs)
                    st.set_output(out)
                    return out
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with span(span_name, kind, capture(args, kwargs)) as st:
                out = fn(*args, **kwargs)
                st.set_output(out)
                return out
        return wrapper

    return deco
