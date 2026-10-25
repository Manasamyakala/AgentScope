"""In-process sink: lets the server's own demo agent write spans straight to the DB
(no HTTP hop). External agents use the SDK's default HTTP sink instead."""
from .db import SessionLocal
from .schemas import SpanIn
from .services.ingest import ingest_spans


def db_sink(batch: list[dict]) -> None:
    with SessionLocal() as db:
        ingest_spans(db, [SpanIn(**b) for b in batch])
