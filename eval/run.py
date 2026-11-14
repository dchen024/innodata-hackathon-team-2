"""Evaluate every valid task with every model and write results/<set>/.

    responses.csv     columns: model, task_id, status, parsed, question_type, response, ref_answer, correct,
                      finish_reason, error   (one row per model x task; very long replies are cut in the CSV cell
                      only - the full text is in responses.jsonl and raw/)
    responses.jsonl   the same rows, full response text, plus usage / cost
    run_config.json   models, temperature, max_tokens, reasoning effort, prompt template, timestamps, total cost
    summary.md        accuracy per model and per question_type, cost
    raw/<model_slug>/<task_id>.json   full API responses

A reported run must be clean: every row status ok, error empty, finish_reason stop. Otherwise this prints a loud
warning and exits nonzero; raise --max-tokens and re-run ALL tasks.
"""
from __future__ import annotations

import csv
import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import openrouter
from .extract import extract
from .prompt import FORMAT_TEXT, PROMPT_TEMPLATE, build_prompt
from .score import is_correct

COLUMNS = ["model", "task_id", "status", "parsed", "question_type", "response", "ref_answer", "correct",
           "finish_reason", "error"]
DEFAULT_MODELS = ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna"]
# The judges' CSV reader uses Python's default field limit (131072 chars); a longer cell makes it read no rows.
CSV_CELL_LIMIT = 100_000
TRUNC_NOTE = "\n...[truncated in CSV; full response in responses.jsonl and raw/{slug}/{task_id}.json]"


ENCRYPTED_NOTE = "[omitted: provider-encrypted reasoning, not readable]"


def drop_encrypted(obj):
    """Replace opaque `reasoning.encrypted` blobs with a note (unreadable, and they can trip secret scanners)."""
    if isinstance(obj, dict):
        if obj.get("type") == "reasoning.encrypted" and "data" in obj:
            obj = {**obj, "data": ENCRYPTED_NOTE}
        return {k: drop_encrypted(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [drop_encrypted(v) for v in obj]
    return obj


def model_slug(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_tasks(task_dir: str | Path) -> tuple[list[dict], list[str]]:
    tasks, skipped = [], []
    for line in (Path(task_dir) / "tasks.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("valid") is False:
            skipped.append(rec.get("task_id"))
            continue
        tasks.append(rec)
    return tasks, skipped


def ref_cell(answer) -> str:
    """The task's answer as text: lists as JSON, numbers as JSON (same as in tasks.jsonl), strings as-is."""
    if isinstance(answer, str):
        return answer
    return json.dumps(answer, ensure_ascii=False)


def parsed_cell(parsed) -> str:
    if parsed is None:
        return ""
    if isinstance(parsed, list):
        return json.dumps(parsed, ensure_ascii=False)
    if isinstance(parsed, float) and parsed.is_integer():
        return str(int(parsed))
    return str(parsed)


def run_one(model: str, task: dict, task_dir: Path, out_dir: Path, max_tokens: int, effort: str) -> dict:
    prompt = build_prompt(task)
    img = task_dir / task["image"]
    res = openrouter.call(model, prompt, str(img), max_tokens=max_tokens, effort=effort)

    fin = res.get("finish_reason")
    if res.get("error"):
        status, error = "api_error", "api_error"
    elif fin == "length":
        status, error = "ok", "length"
    else:
        status, error = "ok", ""
    content = res.get("content") or ""
    parsed = extract(content, task.get("answer_type")) if status == "ok" else None
    correct = is_correct(parsed, task) if not error else ""

    raw_path = out_dir / "raw" / model_slug(model) / f"{task['task_id']}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps({
        "model": model, "task_id": task["task_id"], "time": now(),
        "request": {"prompt": prompt, "image": task["image"], "temperature": 0, "max_tokens": max_tokens,
                    "reasoning": {"effort": effort}, "usage": {"include": True}},
        "content": content, "finish_reason": fin, "native_finish_reason": res.get("native_finish_reason"),
        "parsed": parsed, "ref_answer": task.get("answer"), "correct": correct,
        "usage": res.get("usage"), "cost": res.get("cost"), "error": res.get("error"),
        "attempts": res.get("attempts"), "retry_log": res.get("retry_log"), "latency_s": res.get("latency_s"),
        "response": drop_encrypted(res.get("raw")),
    }, indent=2, ensure_ascii=False))

    return {
        "model": model, "task_id": task["task_id"], "status": status, "parsed": parsed_cell(parsed),
        "question_type": task.get("question_type") or task.get("family") or task.get("answer_type", ""),
        "response": content, "ref_answer": ref_cell(task.get("answer")), "correct": correct,
        "finish_reason": fin or "", "error": error,
        # extras (jsonl / summary only)
        "_answer": task.get("answer"), "_parsed": parsed, "_cost": res.get("cost"), "_usage": res.get("usage"),
        "_native_finish_reason": res.get("native_finish_reason"), "_error_detail": res.get("error"),
        "_attempts": res.get("attempts"),
    }


def write_outputs(rows: list[dict], out_dir: Path) -> None:
    with open(out_dir / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r2 = dict(r)
            if len(r2["response"]) > CSV_CELL_LIMIT:
                note = TRUNC_NOTE.format(slug=model_slug(r["model"]), task_id=r["task_id"])
                r2["response"] = r2["response"][: CSV_CELL_LIMIT - len(note)] + note
            w.writerow(r2)
    with open(out_dir / "responses.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            o = {c: r[c] for c in COLUMNS}
            o["ref_answer"] = r["_answer"]  # native JSON value, identical to tasks.jsonl
            o["parsed"] = r["_parsed"]
            o.update(native_finish_reason=r["_native_finish_reason"], cost=r["_cost"], usage=r["_usage"],
                     error_detail=r["_error_detail"], attempts=r["_attempts"])
            f.write(json.dumps(o, ensure_ascii=False) + "\n")


def summarize(rows: list[dict], models: list[str]) -> tuple[str, dict]:
    by_model = defaultdict(lambda: [0, 0])
    by_qt = defaultdict(lambda: [0, 0])
    cost = defaultdict(float)
    for r in rows:
        if r["correct"] in (0, 1):
            by_model[r["model"]][0] += r["correct"]
            by_model[r["model"]][1] += 1
            by_qt[(r["model"], r["question_type"])][0] += r["correct"]
            by_qt[(r["model"], r["question_type"])][1] += 1
        cost[r["model"]] += float(r["_cost"] or 0)
    lines = ["# Evaluation summary", "", "| Model | Correct | Accuracy | Cost (USD) |", "|---|---|---|---|"]
    for m in models:
        c, n = by_model[m]
        lines.append(f"| `{m}` | {c}/{n} | {c / n:.0%} | {cost[m]:.4f} |" if n else f"| `{m}` | 0/0 | - | "
                     f"{cost[m]:.4f} |")
    qts = sorted({qt for (_, qt) in by_qt})
    lines += ["", "## By question_type", "", "| question_type | " + " | ".join(f"`{m}`" for m in models) + " |",
              "|---|" + "---|" * len(models)]
    for qt in qts:
        cells = []
        for m in models:
            c, n = by_qt.get((m, qt), (0, 0))
            cells.append(f"{c}/{n}" if n else "-")
        lines.append(f"| {qt} | " + " | ".join(cells) + " |")
    lines += ["", "## Per task", "", "| task_id | " + " | ".join(f"`{m}`" for m in models) + " | reference |",
              "|---|" + "---|" * (len(models) + 1)]
    grid = defaultdict(dict)
    refs = {}
    for r in rows:
        mark = {1: "correct", 0: "wrong"}.get(r["correct"], r["error"] or "?")
        grid[r["task_id"]][r["model"]] = f"{mark}: {r['parsed'][:40]}" if r["parsed"] else mark
        refs[r["task_id"]] = r["ref_answer"]
    for tid in sorted(grid):
        lines.append(f"| {tid} | " + " | ".join(grid[tid].get(m, "-").replace("|", "/") for m in models)
                     + f" | {refs[tid][:40].replace('|', '/')} |")
    total = sum(cost.values())
    lines += ["", f"Total cost: ${total:.4f}", ""]
    stats = {"accuracy": {m: {"correct": by_model[m][0], "n": by_model[m][1]} for m in models},
             "cost_by_model": dict(cost), "total_cost": total}
    return "\n".join(lines), stats


def evaluate(task_dir: str, out_dir: str, models: list[str] | None = None, max_tokens: int = 32000,
             workers: int = 6, effort: str = "high", strict: bool = True) -> dict:
    """Run all models x valid tasks. Writes outputs; returns {"clean": bool, ...}.

    With strict=True (default) an unclean run (any error or finish_reason != stop) exits the process with code 1
    after writing everything.
    """
    models = models or DEFAULT_MODELS
    task_dir, out = Path(task_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tasks, skipped = load_tasks(task_dir)
    if skipped:
        print(f"Skipping {len(skipped)} task(s) marked valid=false: {', '.join(map(str, skipped))}\n"
              "  NOTE: the reported tasks.jsonl must hold only accepted tasks - the checker needs a row for every "
              "task in it.")
    if not tasks:
        raise SystemExit(f"No valid tasks in {task_dir}/tasks.jsonl")
    for t in tasks:
        if not (task_dir / t["image"]).is_file():
            raise SystemExit(f"Image missing for {t['task_id']}: {task_dir / t['image']}")

    started = now()
    t0 = time.time()
    jobs = [(m, t) for m in models for t in tasks]
    print(f"Evaluating {len(tasks)} task(s) x {len(models)} model(s) = {len(jobs)} calls "
          f"(max_tokens={max_tokens}, effort={effort}, workers={workers})")
    rows, lock = [], threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one, m, t, task_dir, out, max_tokens, effort): (m, t) for m, t in jobs}
        for fut in as_completed(futs):
            m, t = futs[fut]
            try:
                r = fut.result()
            except Exception as e:  # bug in extraction/scoring etc.: record as an error row, never lose the row
                r = {"model": m, "task_id": t["task_id"], "status": "api_error", "parsed": "",
                     "question_type": t.get("question_type", ""), "response": "", "ref_answer": ref_cell(t["answer"]),
                     "correct": "", "finish_reason": "", "error": "api_error", "_answer": t["answer"],
                     "_parsed": None, "_cost": None, "_usage": None, "_native_finish_reason": None,
                     "_error_detail": f"local exception: {type(e).__name__}: {e}", "_attempts": None}
            with lock:
                rows.append(r)
                tag = {1: "correct", 0: "wrong"}.get(r["correct"], f"ERROR {r['_error_detail'] or r['error']}")
                print(f"[{len(rows)}/{len(jobs)}] {m} {r['task_id']}: {tag} (finish={r['finish_reason'] or '-'}, "
                      f"parsed={r['parsed'][:40]!r})", flush=True)

    order = {(m, t["task_id"]): i for i, (m, t) in enumerate(jobs)}
    rows.sort(key=lambda r: order[(r["model"], r["task_id"])])
    write_outputs(rows, out)
    summary_md, stats = summarize(rows, models)

    bad = [r for r in rows
           if r["status"] != "ok" or r["error"] or r["finish_reason"] != "stop" or not r["response"].strip()]
    clean = not bad
    if not clean:
        summary_md += ("\n**RUN NOT CLEAN**: " + f"{len(bad)} row(s) with an error or finish_reason != stop. "
                       "Do not report this run.\n")
    (out / "summary.md").write_text(summary_md)

    cfg = {
        "models": models,
        "api": openrouter.API_URL,
        "temperature": 0,
        "temperature_note": "temperature=0 is sent on every request, but OpenRouter's model list does not show "
                            "temperature as a supported parameter for these models, so providers may ignore it.",
        "max_tokens": max_tokens,
        "reasoning": {"effort": effort},
        "usage": {"include": True},
        "prompt_template": PROMPT_TEMPLATE,
        "prompt_format_instructions": FORMAT_TEXT,
        "prompt_note": "The user message is [text prompt, image (PNG as base64 data URL)]. The exact prompt for each "
                       "call is saved in raw/<model>/<task_id>.json under request.prompt.",
        "answer_extraction": "last 'FINAL ANSWER:' line of the reply (fallback: last line); see eval/extract.py",
        "scoring": "eval/score.py: numbers within the task's tolerance_rel/tolerance_abs, integers exact, labels "
                   "case/dash/whitespace-insensitive, sequences element-wise, multiple_choice by letter",
        "task_dir": str(task_dir),
        "n_tasks": len(tasks),
        "skipped_invalid_tasks": skipped,
        "workers": workers,
        "max_retries": openrouter.MAX_TRIES,
        "started_at": started,
        "finished_at": now(),
        "duration_s": round(time.time() - t0, 1),
        "clean": clean,
        "accuracy": stats["accuracy"],
        "cost_by_model_usd": stats["cost_by_model"],
        "total_cost_usd": round(stats["total_cost"], 6),
    }
    (out / "run_config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

    print()
    print(summary_md)
    print(f"Wrote {out}/responses.csv, responses.jsonl, run_config.json, summary.md, raw/")
    if not clean:
        bar = "!" * 78
        print(f"\n{bar}\nRUN NOT CLEAN: {len(bad)} of {len(rows)} rows have an API error, finish_reason != stop or an empty reply:",
              file=sys.stderr)
        for r in bad[:20]:
            print(f"  {r['model']} {r['task_id']}: status={r['status']} error={r['error'] or '-'} "
                  f"finish_reason={r['finish_reason'] or '-'} {r['_error_detail'] or ''}", file=sys.stderr)
        print("Do NOT report this run. Raise --max-tokens (for length cut-offs) or fix the API error, then re-run "
              f"ALL tasks.\n{bar}", file=sys.stderr)
        if strict:
            raise SystemExit(1)
    return {"clean": clean, "rows": rows, **stats}
