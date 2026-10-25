"""Demo LangGraph agent: plan -> search -> synthesize -> validate.

Uses a fake deterministic LLM so the project runs with no API keys.
Failure modes are driven by input["config"]["inject_failure"]:
  None     -> healthy run
  "flaky"  -> search API times out once, retry succeeds   (run = degraded)
  "search" -> search API is down on every attempt          (run = failed)
Swap fake_llm() for a real model call and the tracing stays identical.
"""
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

import agentscope


class State(TypedDict, total=False):
    question: str
    config: dict
    plan: list
    docs: list
    answer: str


def fake_llm(label: str, prompt: str, model: str = "demo-llm-1") -> str:
    with agentscope.span(f"llm.{label}", kind="llm", input={"prompt": prompt}) as st:
        time.sleep(0.03)
        text = f"[{label}] " + " ".join(prompt.split()[:12])
        st.set_llm(model, prompt_tokens=len(prompt.split()) + 20, completion_tokens=len(text.split()) + 8)
        st.set_output(text)
        return text


@agentscope.traced("api.search", kind="api")
def search_api(query: str, attempt: int, config: dict) -> list:
    time.sleep(0.04)
    mode = (config or {}).get("inject_failure")
    if mode == "search":
        raise ConnectionError("search API returned 503 Service Unavailable")
    if mode == "flaky" and attempt == 1:
        raise TimeoutError("search API timed out after 2000ms")
    return [f"doc about {query} #1", f"doc about {query} #2"]


def plan_node(state: State) -> State:
    text = fake_llm("plan", f"Break this question into steps: {state['question']}")
    return {"plan": [text, "search", "answer"]}


def search_node(state: State) -> State:
    last_exc = None
    for attempt in (1, 2):  # simple retry policy
        try:
            return {"docs": search_api(state["question"], attempt, state.get("config", {}))}
        except Exception as e:
            last_exc = e
            time.sleep(0.01)
    raise last_exc


def synthesize_node(state: State) -> State:
    docs = " ".join(state.get("docs", []))
    return {"answer": fake_llm("synthesize", f"Answer {state['question']} using {docs}")}


def validate_node(state: State) -> State:
    if not state.get("answer"):
        raise ValueError("empty answer")
    return {}


def _build():
    g = StateGraph(State)
    for name, fn in [("plan", plan_node), ("search", search_node),
                     ("synthesize", synthesize_node), ("validate", validate_node)]:
        g.add_node(name, agentscope.traced(f"node.{name}", kind="node")(fn))
    g.add_edge(START, "plan")
    g.add_edge("plan", "search")
    g.add_edge("search", "synthesize")
    g.add_edge("synthesize", "validate")
    g.add_edge("validate", END)
    return g.compile()


_graph = _build()
WORKFLOW_NAME = "research_agent"


def run_agent(inp: dict, replay_of: str | None = None) -> str:
    """Execute one traced run and return its run id. Failures are recorded, not raised."""
    run_id = ""
    try:
        with agentscope.run(WORKFLOW_NAME, input=inp, replay_of=replay_of) as r:
            run_id = r.trace_id
            result = _graph.invoke({"question": inp["question"], "config": inp.get("config", {})})
            r.set_output({"answer": result.get("answer")})
    except Exception:
        pass  # already captured on the spans
    return run_id
