from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import agentscope

from .api import router
from .config import CORS_ORIGINS
from .db import Base, engine
from .sdk_sink import db_sink


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # swap for Alembic migrations once the schema stabilises
    agentscope.init("agentscope-demo", sink=db_sink, sync=True)
    yield


app = FastAPI(title="AgentScope", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health():
    return {"ok": True}
