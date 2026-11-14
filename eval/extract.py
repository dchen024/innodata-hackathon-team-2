"""Pull the answer out of a model reply (the `parsed` column).

The answer is taken from the LAST "FINAL ANSWER:" in the reply (fallback: the last non-empty line).
Returns: float (number), int (integer), str (label / multiple_choice letter), list[str] (sequence), or None.
"""
from __future__ import annotations

import json
import re

FINAL_RX = re.compile(r"final\s+answer\s*[:：]\s*(.*)", re.I)
NUM_RX = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
MINUS = dict.fromkeys(map(ord, "\u2212\u2012\u2013\u2014\ufe63\uff0d"), "-")


def _strip_markup(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\\boxed\{(.*)\}", r"\1", s)
    s = re.sub(r"^\$+|\$+$", "", s)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = re.sub(r"^\s*[*_>#\-]+\s*", "", s) if not re.match(r"^\s*-\s*\d", s) else s
    return s.strip()


def final_answer_text(response: str) -> str:
    """Text after the last FINAL ANSWER marker; if the marker ends a line, the next non-empty line."""
    if not response:
        return ""
    text = response.replace("\r\n", "\n")
    matches = list(FINAL_RX.finditer(text.replace("**", "")))
    clean = text.replace("**", "")
    if matches:
        m = matches[-1]
        ans = m.group(1).strip()
        if not ans:  # "FINAL ANSWER:\n<answer>"
            rest = [ln for ln in clean[m.end():].split("\n") if ln.strip()]
            ans = rest[0] if rest else ""
        return _strip_markup(ans)
    lines = [ln for ln in clean.split("\n") if ln.strip()]
    return _strip_markup(lines[-1]) if lines else ""


def parse_number(s: str):
    if s is None:
        return None
    s = str(s).translate(MINUS)
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # thousands separators
    s = s.replace("\u00a0", " ")
    s = re.split(r"[=≈~]", s)[-1]  # "x = 12" -> "12"
    m = NUM_RX.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def clean_label(s: str) -> str:
    s = _strip_markup(str(s))
    s = s.strip().strip("\"'“”‘’`").strip()
    s = re.sub(r"[.;,!]+$", "", s).strip()
    s = s.strip("\"'“”‘’`").strip()
    return s


def parse_sequence(s: str):
    s = s.strip()
    m = re.search(r"\[.*\]", s, re.S)
    if m:
        try:
            v = json.loads(m.group(0).replace("“", '"').replace("”", '"'))
            if isinstance(v, list):
                return [clean_label(str(x)) for x in v if str(x).strip()]
        except json.JSONDecodeError:
            pass
        s = m.group(0)
    s = s.strip().strip("[]()")
    parts = re.split(r"\s*(?:->|→|⇒|=>|—>|,|;|\||\bthen\b|\n)\s*", s, flags=re.I)
    parts = [clean_label(p) for p in parts if p and p.strip()]
    if len(parts) <= 1 and parts and " " in parts[0]:
        # Last resort: whitespace-separated short tokens like "E 7 A".
        toks = parts[0].split()
        if all(len(t) <= 3 for t in toks):
            parts = [clean_label(t) for t in toks]
    return [p for p in parts if p]


def parse_choice(s: str):
    s = _strip_markup(s)
    m = re.match(r"^\(?([A-Za-z])\)?(?:[.):\s]|$)", s)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(?:option|answer)\s*\(?([A-Z])\)?\b", s, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([A-Z])\b", s)
    return m.group(1) if m else None


def extract(response: str, answer_type: str):
    ans = final_answer_text(response or "")
    if not ans:
        return None
    if answer_type == "number":
        return parse_number(ans)
    if answer_type == "integer":
        x = parse_number(ans)
        if x is None:
            return None
        return int(x) if float(x).is_integer() else x  # a non-whole reply stays a float and scores wrong
    if answer_type == "multiple_choice":
        return parse_choice(ans)
    if answer_type == "sequence":
        return parse_sequence(ans)
    return clean_label(ans)
