import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_fail_replay_compare():
    with TestClient(app) as c:
        from app.demo.agent import run_agent
        failed = run_agent({"question": "q", "config": {"inject_failure": "search"}})
        r = c.get(f"/api/runs/{failed}").json()
        assert r["run"]["status"] == "failed"
        cause = next(s for s in r["spans"] if s["id"] == r["run"]["root_cause_span_id"])
        assert cause["name"] == "api.search"

        new_id = c.post(f"/api/runs/{failed}/replay",
                        json={"config_overrides": {"inject_failure": None}}).json()["run_id"]
        assert c.get(f"/api/runs/{new_id}").json()["run"]["status"] == "success"

        cmp = c.get(f"/api/runs/{failed}/compare/{new_id}").json()
        assert cmp["divergence"] == "api.search#0"
        assert cmp["summary"]["errors_a"] > 0 and cmp["summary"]["errors_b"] == 0
