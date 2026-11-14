"""Score a parsed answer against the reference, using the task's stated tolerance."""
from __future__ import annotations

import math
import re


def norm_label(z) -> str:
    """Same label normalisation as the organizers' checker (tools/check_submission.py)."""
    z = str(z).lower().replace("&", " and ")
    z = re.sub(r"[^a-z0-9$.\- ]+", " ", z)
    z = re.sub(r"^\s*the\s+", "", z)
    return re.sub(r"\s+", " ", z).strip(" .")


def _as_float(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(",", "").strip())
    except ValueError:
        return None


def _number_ok(parsed, ref, tol_rel=None, tol_abs=None) -> bool:
    p, a = _as_float(parsed), _as_float(ref)
    if p is None or a is None or math.isnan(p):
        return False
    if tol_abs is not None:
        return abs(p - a) <= tol_abs + 1e-12
    if tol_rel is not None:
        return abs(p - a) <= tol_rel * abs(a) + 1e-12
    return abs(p - a) <= 1e-9 * max(1.0, abs(a))


def _item_ok(p, a) -> bool:
    if _as_float(a) is not None and _as_float(p) is not None:
        return _number_ok(p, a)
    return norm_label(p) == norm_label(a)


def is_correct(parsed, task: dict) -> int:
    if parsed is None:
        return 0
    at, ref = task["answer_type"], task["answer"]
    if at == "number":
        ok = _number_ok(parsed, ref, task.get("tolerance_rel"), task.get("tolerance_abs"))
    elif at == "integer":
        p = _as_float(parsed)
        ok = p is not None and p.is_integer() and int(p) == int(ref)
    elif at == "multiple_choice":
        ok = str(parsed).strip().upper() == str(ref).strip().upper()
    elif at == "label":
        ok = norm_label(parsed) == norm_label(ref)
    elif at == "sequence":
        ok = isinstance(parsed, list) and len(parsed) == len(ref) and all(map(_item_ok, parsed, ref))
    else:
        raise ValueError(f"unknown answer_type {at!r}")
    return int(ok)
