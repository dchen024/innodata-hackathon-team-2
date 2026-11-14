"""Family-independent checks on tasks.jsonl records (fields, answer types, tolerance stated, image exists)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

TYPES = ("number", "integer", "label", "multiple_choice", "sequence")


def check_record(rec: dict, task_dir: Path) -> dict:
    problems = []
    for k in ("task_id", "image", "question", "answer", "answer_type", "seed", "generator_version"):
        if k not in rec:
            problems.append(f"missing {k}")
    t = rec.get("answer_type")
    a = rec.get("answer")
    if t not in TYPES:
        problems.append(f"bad answer_type {t}")
    if t == "integer" and not (isinstance(a, int) and not isinstance(a, bool)):
        problems.append("integer answer is not an int")
    if t == "sequence" and not isinstance(a, list):
        problems.append("sequence answer is not a list")
    try:
        non_integer = t == "number" and not float(a).is_integer()
    except (TypeError, ValueError):
        problems.append("number answer is not numeric")
        non_integer = False
    if non_integer:
        tol = [k for k in ("tolerance_rel", "tolerance_abs") if k in rec]
        if len(tol) != 1:
            problems.append("non-integer number needs exactly one tolerance")
        elif not re.search(r"±|within", rec["question"]):
            problems.append("tolerance not stated in question")
    img = task_dir / rec.get("image", "")
    if not img.exists():
        problems.append("image missing")
    elif rec.get("image_sha256") and hashlib.sha256(img.read_bytes()).hexdigest() != rec["image_sha256"]:
        problems.append("image hash differs from record")
    return {"schema": dict(passed=not problems, problems=problems)}
