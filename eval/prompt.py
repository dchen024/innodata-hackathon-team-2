"""The exact prompt sent to the models (saved into run_config.json)."""
from __future__ import annotations

INSTRUCTIONS = (
    "Answer the question about the image. Think it through, then end your reply with a final line of the form\n"
    "FINAL ANSWER: <answer>\n"
)

FORMATS = {
    "number": "Give the answer as a plain number, without units.",
    "integer": "Give the answer as a whole number, without units.",
    "label": "Give the answer exactly as it is written in the image.",
    "multiple_choice": "Give only the letter of the correct option.",
    "sequence": "Give the items in order, separated by commas, each written exactly as in the image.",
}

PROMPT_TEMPLATE = (
    "{question}\n\n"
    "[multiple_choice only] Options:\nA. ...\nB. ...\n\n"
    "{format line for the answer_type}\n"
    "[number with tolerance only] Your answer counts as correct if it is within ±{tolerance} of the true value.\n\n"
    + INSTRUCTIONS
)


def tolerance_text(task: dict) -> str | None:
    if task.get("tolerance_rel") is not None:
        return f"{task['tolerance_rel'] * 100:g}%"
    if task.get("tolerance_abs") is not None:
        return f"{task['tolerance_abs']:g}"
    return None


def build_prompt(task: dict) -> str:
    at = task["answer_type"]
    if at not in FORMATS:
        raise ValueError(f"unknown answer_type {at!r}")
    parts = [task["question"].strip()]
    if at == "multiple_choice":
        options = task.get("options") or []
        if not options:
            raise ValueError(f"{task.get('task_id')}: multiple_choice task without options")
        parts.append("Options:\n" + "\n".join(f"{chr(65 + i)}. {o}" for i, o in enumerate(options)))
    fmt = FORMATS[at]
    tol = tolerance_text(task)
    if tol is not None:
        fmt += f"\nYour answer counts as correct if it is within ±{tol} of the true value."
    parts.append(fmt)
    parts.append(INSTRUCTIONS)
    return "\n\n".join(parts)
