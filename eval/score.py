"""Score a parsed answer against the reference, using the task's stated tolerance."""
from __future__ import annotations

import json
import re
import unicodedata

DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
QUOTES = dict.fromkeys(map(ord, "‘’‚‛′"), "'")


def norm_label(s) -> str:
    """Case-insensitive; unify dashes, quotes, whitespace; 'St.' == 'St'; trailing period ignored."""
    s = unicodedata.normalize("NFKC", str(s)).translate(DASHES).translate(QUOTES)
    s = s.replace("**", "").strip().strip("\"'`“”").lower()
    s = re.sub(r"\s*-\s*", "-", s)          # "Times Sq - 42 St" == "Times Sq-42 St"
    s = re.sub(r"\bst\.", "st", s)           # "St." == "St"
    s = re.sub(r"\bave\.", "ave", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^the\s+", "", s)
    return s.strip(" .;,")


def _num(x):
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    from .extract import parse_number
    return parse_number(str(x))


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            v = json.loads(x)
            if isinstance(v, list):
                return v
        except json.JSONDecodeError:
            pass
        from .extract import parse_sequence
        return parse_sequence(x)
    return None


def is_correct(parsed, task: dict) -> int:
    if parsed is None or parsed == "" or parsed == []:
        return 0
    at, ref = task.get("answer_type"), task.get("answer")
    if at in ("number", "integer"):
        x, r = _num(parsed), _num(ref)
        if x is None or r is None:
            return 0
        if at == "integer" and task.get("tolerance_abs") is None and task.get("tolerance_rel") is None:
            return int(x == r)
        tol = 1e-9 * max(1.0, abs(r))
        if task.get("tolerance_abs") is not None:
            tol = max(tol, float(task["tolerance_abs"]))
        elif task.get("tolerance_rel") is not None:
            tol = max(tol, float(task["tolerance_rel"]) * abs(r))
        return int(abs(x - r) <= tol + 1e-12)
    if at == "multiple_choice":
        return int(str(parsed).strip().upper()[:1] == str(ref).strip().upper()[:1])
    if at == "sequence":
        got, want = _as_list(parsed), _as_list(ref)
        if got is None or want is None or len(got) != len(want):
            return 0
        return int(all(norm_label(a) == norm_label(b) for a, b in zip(got, want)))
    return int(norm_label(parsed) == norm_label(ref))
