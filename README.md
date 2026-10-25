# AgentScope

Find out *which step* made your AI agent fail. Records reasoning steps, tool/API calls,
latency, token usage and errors as OpenTelemetry spans; visualises the execution flow;
and lets you **replay a failed run and diff it against a successful one**.

## Run it (backend, no Docker)
```bash
pip install ./sdk -r backend/requirements.txt
cd backend
python -m scripts.seed          
uvicorn app.main:app --reload   
pytest                          
```
## Run it (Docker + Postgres)
```bash
docker compose up --build
```
## Instrument your own agent
```python
import agentscope
agentscope.init("my-service", endpoint="http://localhost:8000")

@agentscope.traced("tool.lookup", kind="tool")
def lookup(q): ...

with agentscope.run("my_agent", input={"question": "..."}):
    ...
```
## Layout
- `sdk/` – pip-installable tracing SDK (OpenTelemetry → AgentScope exporter)
- `backend/app/` – FastAPI: ingest, runs, compare, replay, stats
- `backend/app/demo/` – LangGraph demo agent with failure injection
- `frontend/` – React + Recharts dashboard (Phase 2)
