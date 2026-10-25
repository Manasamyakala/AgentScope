from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Run(Base):
    """One agent execution (== one OpenTelemetry trace). Aggregates are derived from spans."""
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # trace_id
    name: Mapped[str] = mapped_column(String(200), default="(pending)", index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # running|success|degraded|failed
    started_ns: Mapped[int | None] = mapped_column(BigInteger)
    ended_ns: Mapped[int | None] = mapped_column(BigInteger)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    input: Mapped[dict | None] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON)
    replay_of: Mapped[str | None] = mapped_column(String(32), index=True)
    root_cause_span_id: Mapped[str | None] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Span(Base):
    """One step: node, LLM call, tool call, API call, ..."""
    __tablename__ = "spans"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # span_id
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[str | None] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    start_ns: Mapped[int] = mapped_column(BigInteger)
    end_ns: Mapped[int] = mapped_column(BigInteger)
    duration_ms: Mapped[float] = mapped_column(Float)
    input: Mapped[dict | list | str | None] = mapped_column(JSON)
    output: Mapped[dict | list | str | None] = mapped_column(JSON)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String(100))
    error_type: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSON)
