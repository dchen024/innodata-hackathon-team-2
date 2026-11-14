"""Evaluate every valid task with every model and write results/<set>/.

    responses.csv     columns: model, task_id, status, parsed, question_type, response, ref_answer, correct,
                      finish_reason, error   (one row per model x task)
    run_config.json   models, temperature, max_tokens, reasoning effort, prompt, timestamps, total cost
    raw/<model>/<task_id>.json   full API responses
    errors.jsonl      one line per call that needed a retry or failed

Reruns reuse raw/ files whose call succeeded, so only missing or failed calls are paid for again.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import openrouter
from .extract import extract
from .prompt import INSTRUCTIONS, PROMPT_TEMPLATE, build_prompt
from .score import is_correct

COLUMNS = ["model", "task_id", "status", "parsed", "question_type", "response", "ref_answer", "correct",
           "finish_reason", "error"]
CSV_CELL_MAX = 100_000  # the judge's CSV reader fails on cells over 131072 characters; full text stays in raw/


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_tasks(task_dir: Path) -> list[dict]:
    """Tasks from tasks.jsonl, minus any listed as failed in checks.json ({"failed": [task_id, ...]})."""
    tasks = [json.loads(ln) for ln in (task_dir / "tasks.jsonl").read_text().splitlines() if ln.strip()]
    checks = task_dir / "checks.json"
    if checks.exists():
        failed = set(json.loads(checks.read_text()).get("failed") or [])
        skipped = [t["task_id"] for t in tasks if t["task_id"] in failed]
        if skipped:
            print(f"skipping {len(skipped)} task(s) that failed validation: {', '.join(skipped)}", file=sys.stderr)
        tasks = [t for t in tasks if t["task_id"] not in failed]
    return tasks


def _image_path(task_dir: Path, task: dict) -> Path:
    p = task_dir / task["image"]
    return p if p.exists() else Path(task["image"])


def _raw_path(out_dir: Path, model: str, task_id: str) -> Path:
    return out_dir / "raw" / model.replace("/", "__") / f"{task_id}.json"


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _run_one(task_dir: Path, out_dir: Path, model: str, task: dict, max_tokens: int, effort: str) -> dict:
    raw_path = _raw_path(out_dir, model, task["task_id"])
    if raw_path.exists():
        cached = json.loads(raw_path.read_text())
        if cached.get("error") == "" and cached.get("prompt") == build_prompt(task) \
                and cached.get("max_tokens") == max_tokens and cached.get("effort") == effort:
            cached["cached"] = True
            return cached
    prompt = build_prompt(task)
    started = _now()
    result = openrouter.call(model, prompt, str(_image_path(task_dir, task)), max_tokens=max_tokens, effort=effort)
    record = {"task_id": task["task_id"], "prompt": prompt, "max_tokens": max_tokens, "effort": effort,
              "temperature": openrouter.TEMPERATURE, "started_at": started, "finished_at": _now(), **result}
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    record["cached"] = False
    return record


def _row(task: dict, rec: dict) -> dict:
    error = rec["error"]
    parsed = extract(rec["content"], task["answer_type"]) if not error else None
    response = rec["content"]
    if len(response) > CSV_CELL_MAX:
        response = response[:CSV_CELL_MAX] + " …[truncated, full reply in raw/]"
    return {
        "model": rec["model"],
        "task_id": task["task_id"],
        "status": "api_error" if error == "api_error" else "ok",
        "parsed": _cell(parsed),
        "question_type": task["question_type"],
        "response": response,
        "ref_answer": _cell(task["answer"]),
        "correct": "" if error else is_correct(parsed, task),
        "finish_reason": rec["finish_reason"],
        "error": error,
    }


def evaluate(task_dir: str, out_dir: str, models: list[str], max_tokens: int, effort: str = "high",
             workers: int = 4) -> None:
    task_dir, out_dir = Path(task_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(task_dir)
    if not tasks:
        raise SystemExit(f"no tasks to evaluate in {task_dir}")
    for t in tasks:  # fail before spending money
        build_prompt(t)
        if not _image_path(task_dir, t).exists():
            raise SystemExit(f"{t['task_id']}: image not found: {t['image']}")
    started = _now()
    by_id = {t["task_id"]: t for t in tasks}
    jobs = [(m, t) for m in models for t in tasks]
    records: dict[tuple[str, str], dict] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, task_dir, out_dir, m, t, max_tokens, effort): (m, t["task_id"])
                   for m, t in jobs}
        for i, fut in enumerate(as_completed(futures), 1):
            key = futures[fut]
            rec = fut.result()
            records[key] = rec
            tag = "cached" if rec.get("cached") else (rec["error"] or "ok")
            print(f"[{i}/{len(jobs)}] {key[0]} {key[1]}: {tag}", file=sys.stderr)

    rows = [_row(by_id[tid], records[(m, tid)]) for m in models for tid in sorted(by_id)]
    with open(out_dir / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    with open(out_dir / "errors.jsonl", "w", encoding="utf-8") as f:
        for (m, tid), rec in sorted(records.items()):
            if rec.get("attempt_errors") or rec["error"]:
                f.write(json.dumps({"model": m, "task_id": tid, "error": rec["error"], "attempts": rec.get("attempts"),
                                    "attempt_errors": rec.get("attempt_errors", [])}, ensure_ascii=False) + "\n")

    summary = defaultdict(lambda: {"tasks": 0, "correct": 0, "api_error": 0, "length": 0, "cost": 0.0})
    for row in rows:
        s = summary[row["model"]]
        s["tasks"] += 1
        s["correct"] += row["correct"] == 1
        if row["error"]:
            s[row["error"]] += 1
    for (m, _), rec in records.items():
        summary[m]["cost"] += rec.get("cost") or 0.0
    total_cost = sum(s["cost"] for s in summary.values())

    config = {
        "task_set": str(task_dir),
        "models": models,
        "temperature": openrouter.TEMPERATURE,
        "max_tokens": max_tokens,
        "reasoning": {"effort": effort},
        "api_url": openrouter.API_URL,
        "max_attempts": openrouter.MAX_ATTEMPTS,
        "instructions_prompt": INSTRUCTIONS,
        "prompt_template": PROMPT_TEMPLATE,
        "task_prompts": [build_prompt(by_id[tid]) for tid in sorted(by_id)],
        "n_tasks": len(tasks),
        "started_at": started,
        "finished_at": _now(),
        "total_cost_usd": round(total_cost, 6),
        "summary": {m: {**s, "cost": round(s["cost"], 6)} for m, s in summary.items()},
    }
    (out_dir / "run_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False))

    for m, s in summary.items():
        print(f"{m}: {s['correct']}/{s['tasks']} correct, {s['api_error']} api_error, {s['length']} length, "
              f"${s['cost']:.4f}", file=sys.stderr)
    bad = sum(s["api_error"] + s["length"] for s in summary.values())
    if bad:
        print(f"WARNING: {bad} incomplete response(s). The submission check requires none: see errors.jsonl, "
              "raise --max-tokens for `length`, then rerun (successful calls are reused).", file=sys.stderr)
