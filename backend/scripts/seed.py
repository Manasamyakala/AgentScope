"""Populate demo data: python -m scripts.seed   (run from backend/)"""
import agentscope

from app.db import Base, engine
from app.demo.agent import run_agent
from app.sdk_sink import db_sink

Base.metadata.create_all(engine)
agentscope.init("seed", sink=db_sink, sync=True)

questions = ["What is LangGraph?", "Explain OpenTelemetry spans", "Why do agents fail?"]
for q in questions:
    run_agent({"question": q, "config": {}})
    run_agent({"question": q, "config": {"inject_failure": "flaky"}})
failed = run_agent({"question": questions[0], "config": {"inject_failure": "search"}})
print("seeded. failed run id:", failed)
