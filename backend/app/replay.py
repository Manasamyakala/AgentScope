"""Registry of workflows the server is able to re-execute for replay.
Register your own agent here: WORKFLOWS["my_agent"] = my_run_function
(signature: fn(input: dict, replay_of: str | None) -> run_id)."""
from .demo.agent import WORKFLOW_NAME, run_agent

WORKFLOWS = {WORKFLOW_NAME: run_agent}
