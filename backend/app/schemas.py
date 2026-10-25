from typing import Any

from pydantic import BaseModel, Field


class SpanIn(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str = "step"
    status: str = "ok"
    start_ns: int
    end_ns: int
    input: Any = None
    output: Any = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class IngestIn(BaseModel):
    spans: list[SpanIn]


class ReplayIn(BaseModel):
    # Shallow-merged into input["config"] before re-running, e.g. {"inject_failure": None}
    config_overrides: dict[str, Any] = Field(default_factory=dict)
