"""End to end against the organizers' format checker: built tasks -> eval (OpenRouter faked) -> results folder,
then tools/check_submission.py's task and results checks report no FAIL."""
from __future__ import annotations

import json
import shutil
import sys

import pytest

from tests.conftest import ROOT, NetworkBlocked, read_jsonl

sys.path.insert(0, str(ROOT / "tools"))
import check_submission as cs  # noqa: E402
from eval import openrouter, run  # noqa: E402

MODELS = ["prov/model-a", "prov/model-b"]


def reply_for(task, wrong=False):
    a = task["answer"]
    if wrong:
        a = (a + 1) if isinstance(a, int) else (a[::-1] + ["Z"] if isinstance(a, list) else a + " X")
    body = json.dumps(a) if isinstance(a, list) else str(a)
    return f"Reading the map...\nFINAL ANSWER: {body}"


@pytest.fixture
def submission(built_set, tmp_path, monkeypatch):
    sub = tmp_path / "repo"
    tdir = sub / "tasks" / "final"
    shutil.copytree(built_set["dir"], tdir)
    valid = [r for r in read_jsonl(tdir / "tasks.jsonl") if r["valid"]]          # the reported set
    (tdir / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in valid))
    by_id = {r["task_id"]: r for r in valid}

    def fake_call(model, prompt, png_path, *, max_tokens, effort):
        t = by_id[png_path.rsplit("/", 1)[-1][:-4]]
        assert t["question"] in prompt
        return {"model": model, "content": reply_for(t, wrong=model.endswith("-b") and t["task_id"] == valid[0]["task_id"]),
                "finish_reason": "stop", "native_finish_reason": "stop", "usage": {"cost": 0.0}, "cost": 0.0,
                "raw": {}, "error": None, "attempts": 1, "latency_s": 0.0, "retry_log": []}

    monkeypatch.setattr(run.openrouter, "call", fake_call)
    rdir = sub / "results" / "final"
    out = run.evaluate(str(tdir), str(rdir), MODELS, max_tokens=1000, workers=2)
    return dict(sub=sub, tasks=valid, results=rdir, ret=out)


def test_eval_scores_real_answers(submission):
    rows = read_jsonl(submission["results"] / "responses.jsonl")
    assert len(rows) == 2 * len(submission["tasks"])
    wrong = [(r["model"], r["task_id"]) for r in rows if r["correct"] != 1]
    assert wrong == [(MODELS[1], submission["tasks"][0]["task_id"])]
    assert all(r["status"] == "ok" and r["error"] == "" and r["finish_reason"] == "stop" for r in rows)
    assert all(r["ref_answer"] == next(t["answer"] for t in submission["tasks"] if t["task_id"] == r["task_id"])
               for r in rows)


def test_checker_finds_no_fail(submission):
    rep = cs.Report()
    sub = cs.Submission(submission["sub"])
    tasks = cs.check_tasks(rep, sub, "tasks/final", len(submission["tasks"]), "")
    cs.check_results(rep, sub, "results/final", tasks)
    fails = [(sec, m) for sec, lvl, m in rep.items if lvl == "FAIL"]
    assert fails == []
    cfg = json.loads((submission["results"] / "run_config.json").read_text())
    assert cfg["temperature"] == 0 and cfg["models"] == MODELS


def test_openrouter_cannot_reach_network(tmp_path, monkeypatch):
    """Guard self-test: even with a key present, a real call is blocked before any request leaves."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test-not-a-real-key")
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG fake")
    with pytest.raises(NetworkBlocked):
        openrouter.call("prov/m", "hi", str(png), max_tokens=10, effort="low")


def test_review_client_cannot_be_constructed():
    import anthropic
    with pytest.raises(NetworkBlocked):
        anthropic.Anthropic()
