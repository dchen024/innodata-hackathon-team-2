"""Adversarial validity review of a task folder with Claude (Anthropic API).

For each task the reviewer gets the image, the question, the task's data JSON (if the record has a `data` path or
object) and the reference answer. It is told to solve the question from the image first, then try to show the
task is INVALID (wrong reference, ambiguous question, information not visible/legible, answerable without the
image, unfair tolerance), and to end with a JSON verdict.

    python -m validate.review --tasks tasks/pilot [--model claude-opus-5-5] [--limit N] [--workers 4]

Writes <task_dir>/review.json and prints a summary. Key: ANTHROPIC_API_KEY from the environment or .env.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from eval.openrouter import load_dotenv
from eval.score import is_correct

DEFAULT_MODEL = "claude-opus-5-5"
DATA_CHAR_LIMIT = 20_000
MAX_TOKENS = 32_000
PRICE_PER_MTOK = {"claude-opus-5-5": (4.0, 20.0)}  # input, output USD (estimate for the summary only)

SYSTEM = """You are an adversarial auditor of visual question-answering benchmark tasks. Each task is a rendered \
transit (subway) map image, a question, and a reference answer computed by code from the map's underlying data. \
Your job is to try to show that the task is INVALID. A task is valid only if a careful human reading the image \
alone would reach exactly the reference answer, and no other defensible answer exists.

Look for these failure modes:
1. reference_wrong - the reference answer does not match what the image shows (or what the data implies).
2. ambiguous - the question admits more than one defensible answer (unclear wording, ties, unclear counting rules, \
unclear start/end, several equally short routes, unclear whether endpoints count, etc.).
3. not_visible - information needed to answer is missing, hidden, overlapping, cut off, too small or illegible in \
the image (labels colliding, lines indistinguishable in colour, etc.).
4. answerable_without_image - the answer can be derived from the question text alone or from general knowledge.
5. unfair_tolerance - a numeric tolerance that is too tight for a visual estimate, or so loose that guessing works.
6. format - the requested answer format is unclear or the reference is written differently from the map labels.

Be rigorous and concrete: cite what you see in the image (positions, labels, colours). Do not invent problems; if \
you cannot find a real issue after a genuine attempt, say the task is valid."""

INSTRUCTIONS = """Work in this order:
STEP 1 - Solve the question yourself from the image only, as a careful human would, before you look at the \
reference answer or the data below. Write out your reading of the image and your independent answer.
STEP 2 - Now read the reference answer (and the data JSON, if given). Compare. Then attack the task using the \
failure modes in your instructions.
STEP 3 - End your reply with one JSON object in a ```json code block, exactly these keys:
{"verdict": "valid" | "invalid" | "unsure",
 "independent_answer": <your STEP 1 answer, in the same format the question asks for>,
 "issues": [{"type": "reference_wrong|ambiguous|not_visible|answerable_without_image|unfair_tolerance|format|other", \
"detail": "<one or two sentences>"}],
 "severity": "none" | "minor" | "major"}
Use "invalid" with severity "major" when the reference is wrong or the task has more than one defensible answer; \
"minor" for issues that do not change the answer (e.g. small legibility problems)."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_records(task_dir: Path) -> list[dict]:
    return [json.loads(l) for l in (task_dir / "tasks.jsonl").read_text().splitlines() if l.strip()]


def data_text(rec: dict, task_dir: Path) -> tuple[str | None, bool]:
    """(data JSON text or None, was_truncated). `data` may be a path relative to the task folder or an object."""
    d = rec.get("data") or rec.get("data_path")
    if d is None:
        return None, False
    if isinstance(d, (dict, list)):
        txt = json.dumps(d, ensure_ascii=False)
    else:
        p = task_dir / str(d)
        if not p.is_file():
            return None, False
        txt = p.read_text()
        try:  # compact it to fit more into the limit
            txt = json.dumps(json.loads(txt), ensure_ascii=False, separators=(",", ":"))
        except json.JSONDecodeError:
            pass
    if len(txt) > DATA_CHAR_LIMIT:
        return txt[:DATA_CHAR_LIMIT] + "\n...[data truncated to fit; remaining characters omitted]", True
    return txt, False


def build_content(rec: dict, task_dir: Path) -> tuple[list, bool]:
    img = base64.standard_b64encode((task_dir / rec["image"]).read_bytes()).decode("ascii")
    tol = {k: rec[k] for k in ("tolerance_rel", "tolerance_abs") if rec.get(k) is not None}
    parts = [f"QUESTION (exactly as shown to the models under test):\n{rec['question']}\n",
             f"Answer type: {rec.get('answer_type')}" + (f"; options: {json.dumps(rec['options'])}"
                                                         if rec.get("options") else ""),
             "\n" + INSTRUCTIONS,
             "\n----- Material for STEP 2 only (do not use it in STEP 1) -----",
             f"REFERENCE ANSWER: {json.dumps(rec.get('answer'), ensure_ascii=False)}"
             + (f"\nTolerance used for scoring: {json.dumps(tol)}" if tol else "")]
    dtxt, truncated = data_text(rec, task_dir)
    if dtxt:
        parts.append(f"\nDATA JSON the image and answer were generated from:\n{dtxt}")
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img}},
        {"type": "text", "text": "\n".join(parts)},
    ], truncated


def parse_verdict(text: str) -> dict | None:
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = blocks[::-1] or []
    if not cands:  # last {...} in the text
        i = text.rfind('{"verdict"')
        if i < 0:
            i = text.rfind("{")
        if i >= 0:
            cands = [text[i:text.rfind("}") + 1]]
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, dict) and "verdict" in v:
                return v
        except json.JSONDecodeError:
            continue
    return None


def review_one(client: anthropic.Anthropic, model: str, rec: dict, task_dir: Path) -> dict:
    out = {"task_id": rec.get("task_id"), "question_type": rec.get("question_type"),
           "reference": rec.get("answer"), "model": model}
    try:
        content, truncated = build_content(rec, task_dir)
        out["data_truncated"] = truncated
        kwargs = dict(model=model, max_tokens=MAX_TOKENS, system=SYSTEM,
                      thinking={"type": "adaptive"}, output_config={"effort": "high"},
                      messages=[{"role": "user", "content": content}])
        if model.startswith("claude-opus-5-5"):
            # Server-side refusal fallback: a classifier decline is re-run on a fallback model in the same call.
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        with client.beta.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
    except anthropic.APIStatusError as e:
        out.update(verdict="error", error=f"HTTP {e.status_code}: {str(e)[:500]}")
        return out
    except anthropic.APIConnectionError as e:
        out.update(verdict="error", error=f"connection: {str(e)[:300]}")
        return out
    except Exception as e:  # local problems: missing image etc.
        out.update(verdict="error", error=f"{type(e).__name__}: {e}")
        return out

    text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    out.update(stop_reason=msg.stop_reason, served_by=msg.model, review_text=text,
               usage={"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens})
    if msg.stop_reason == "refusal":
        out.update(verdict="unsure", severity="none", issues=[{"type": "other", "detail": "reviewer refused"}])
        return out
    v = parse_verdict(text)
    if v is None:
        out.update(verdict="unsure", severity="none", issues=[{"type": "other", "detail":
                   f"could not parse reviewer JSON (stop_reason={msg.stop_reason})"}])
        return out
    out.update(verdict=str(v.get("verdict", "unsure")).lower(), independent_answer=v.get("independent_answer"),
               issues=v.get("issues") or [], severity=str(v.get("severity", "none")).lower())
    try:
        ia = v.get("independent_answer")
        if rec.get("answer_type") == "sequence" and isinstance(ia, str):
            from eval.extract import parse_sequence
            ia = parse_sequence(ia)
        out["independent_agrees"] = bool(is_correct(ia, rec))
    except Exception:
        out["independent_agrees"] = None
    return out


def review(task_dir: str, model: str = DEFAULT_MODEL, limit: int | None = None, workers: int = 4) -> dict:
    task_dir = Path(task_dir)
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("note: ANTHROPIC_API_KEY not set; relying on other SDK credentials (e.g. `ant auth login`)",
              file=sys.stderr)
    client = anthropic.Anthropic(max_retries=5)
    recs = load_records(task_dir)[: limit or None]
    print(f"Reviewing {len(recs)} task(s) in {task_dir} with {model} ...")
    results, lock = [], threading.Lock()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(review_one, client, model, r, task_dir) for r in recs]
        for f in as_completed(futs):
            r = f.result()
            with lock:
                results.append(r)
                print(f"[{len(results)}/{len(recs)}] {r['task_id']}: {r['verdict']}"
                      f" ({r.get('severity', '-')}) agrees={r.get('independent_agrees')}", flush=True)
    order = {r.get("task_id"): i for i, r in enumerate(recs)}
    results.sort(key=lambda r: order.get(r["task_id"], 0))

    tin = sum((r.get("usage") or {}).get("input_tokens", 0) for r in results)
    tout = sum((r.get("usage") or {}).get("output_tokens", 0) for r in results)
    pi, po = PRICE_PER_MTOK.get(model, (0.0, 0.0))
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    report = {"model": model, "time": now(), "task_dir": str(task_dir), "n": len(results), "counts": counts,
              "input_tokens": tin, "output_tokens": tout, "est_cost_usd": round(tin / 1e6 * pi + tout / 1e6 * po, 4),
              "results": results}
    (task_dir / "review.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n=== Review summary ===")
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    for r in results:
        if r["verdict"] != "valid" or r.get("independent_agrees") is False:
            issues = "; ".join(f"{i.get('type')}: {i.get('detail')}" if isinstance(i, dict) else str(i)
                               for i in (r.get("issues") or [])) or r.get("error", "")
            print(f"- {r['task_id']} [{r['verdict']}/{r.get('severity', '-')}] ref={json.dumps(r['reference'])} "
                  f"reviewer={json.dumps(r.get('independent_answer'))}\n    {issues[:600]}")
    print(f"tokens in/out: {tin}/{tout}, est. cost ${report['est_cost_usd']}")
    print(f"Wrote {task_dir / 'review.json'}")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m validate.review", description=__doc__.split("\n\n")[0])
    p.add_argument("--tasks", required=True, help="task folder holding tasks.jsonl and images/")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--limit", type=int, default=None, help="review only the first N tasks")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args(argv)
    review(a.tasks, a.model, a.limit, a.workers)


if __name__ == "__main__":
    main()
