"""End-to-end eval run with the OpenRouter call faked, checked against the organizers' rules."""
import csv
import json
import sys
from pathlib import Path

from eval import run

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check_submission as cs  # noqa: E402

TASKS = [
    {"task_id": "t1", "image": "images/t1.png", "question": "How many minutes?", "answer": 12,
     "answer_type": "integer", "question_type": "travel_time"},
    {"task_id": "t2", "image": "images/t2.png", "question": "Which line? Answer within ±5%.", "answer": 31.5,
     "answer_type": "number", "tolerance_rel": 0.05, "question_type": "distance"},
    {"task_id": "t3", "image": "images/t3.png", "question": "Which stop?", "answer": "B",
     "answer_type": "multiple_choice", "options": ["Alpha", "Beta"], "question_type": "stop"},
    {"task_id": "t4", "image": "images/t4.png", "question": "Order?", "answer": ["A", "B"],
     "answer_type": "sequence", "question_type": "order"},
]
REPLIES = {"t1": "FINAL ANSWER: 12", "t2": "FINAL ANSWER: 40", "t3": "FINAL ANSWER: B", "t4": "FINAL ANSWER: A, B"}


def make_tasks(tmp_path):
    d = tmp_path / "tasks"
    (d / "images").mkdir(parents=True)
    for t in TASKS:
        (d / t["image"]).write_bytes(b"\x89PNG fake")
    (d / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in TASKS) + "\n")
    return d


def fake_call(calls, *, length_for=None, fail_for=None):
    def call(model, prompt, png_path, *, max_tokens, effort):
        tid = Path(png_path).stem
        calls.append((model, tid))
        base = {"model": model, "native_finish_reason": "", "reasoning": "", "usage": {"cost": 0.01},
                "cost": 0.01, "attempts": 1, "attempt_errors": [], "response": {}}
        if tid == length_for:
            return {**base, "finish_reason": "length", "content": "", "error": "length"}
        if tid == fail_for:
            return {**base, "finish_reason": "", "content": "", "error": "api_error", "attempt_errors": ["HTTP 500"]}
        return {**base, "finish_reason": "stop", "content": "thinking...\n" + REPLIES[tid], "error": ""}
    return call


def read_rows(out):
    with open(out / "responses.csv", newline="") as f:
        return list(csv.DictReader(f))


def test_full_run(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run.openrouter, "call", fake_call(calls))
    tasks, out = make_tasks(tmp_path), tmp_path / "results"
    run.evaluate(str(tasks), str(out), ["prov/a", "prov/b"], 1000)

    rows = read_rows(out)
    assert list(rows[0]) == run.COLUMNS and len(rows) == 8
    assert [r["correct"] for r in rows[:4]] == ["1", "0", "1", "1"]
    for r in rows:
        assert cs.same_reference(r["ref_answer"], next(t["answer"] for t in TASKS if t["task_id"] == r["task_id"]))
    assert (out / "raw" / "prov__a" / "t1.json").exists()
    cfg = json.loads((out / "run_config.json").read_text())
    assert cfg["temperature"] == 0 and cfg["max_tokens"] == 1000 and cfg["total_cost_usd"] == 0.08

    # a rerun reuses every successful call
    calls.clear()
    run.evaluate(str(tasks), str(out), ["prov/a", "prov/b"], 1000)
    assert calls == []


def test_errors_follow_checker_rules(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run.openrouter, "call", fake_call(calls, length_for="t1", fail_for="t2"))
    tasks, out = make_tasks(tmp_path), tmp_path / "results"
    run.evaluate(str(tasks), str(out), ["prov/a"], 1000)

    by_id = {r["task_id"]: r for r in read_rows(out)}
    assert (by_id["t1"]["error"], by_id["t1"]["finish_reason"], by_id["t1"]["correct"]) == ("length", "length", "")
    assert (by_id["t2"]["status"], by_id["t2"]["error"], by_id["t2"]["correct"]) == ("api_error", "api_error", "")
    assert len((out / "errors.jsonl").read_text().splitlines()) == 2

    # failed calls are retried on the next run, successful ones are not
    calls.clear()
    run.evaluate(str(tasks), str(out), ["prov/a"], 1000)
    assert sorted(tid for _, tid in calls) == ["t1", "t2"]


def test_checks_json_skips_failed_tasks(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(run.openrouter, "call", fake_call(calls))
    tasks, out = make_tasks(tmp_path), tmp_path / "results"
    (tasks / "checks.json").write_text(json.dumps({"failed": ["t3"]}))
    run.evaluate(str(tasks), str(out), ["prov/a"], 1000)
    assert {r["task_id"] for r in read_rows(out)} == {"t1", "t2", "t4"}
