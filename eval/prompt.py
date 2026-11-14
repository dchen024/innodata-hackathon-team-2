"""The exact prompt sent to the models (saved into run_config.json).

prompt = PROMPT_TEMPLATE.format(question=..., format_instructions=FORMAT_INSTRUCTIONS[answer_type](task))
"""
from __future__ import annotations

PROMPT_TEMPLATE = (
    "{question}\n"
    "\n"
    "Answer the question using the image. Think it through, then {format_instructions}\n"
    "End your reply with a final line of the form:\n"
    "FINAL ANSWER: <answer>"
)

# Kept as plain strings so run_config.json can record them verbatim.
FORMAT_TEXT = {
    "number": "give the answer as a single number (digits only, no units).",
    "integer": "give the answer as a single whole number (digits only, no units).",
    "label": "give the answer exactly as written on the map (just the name, nothing else).",
    "multiple_choice": "give the answer as the single letter of the correct option.",
    "sequence": 'give the answer as a JSON list of names exactly as written on the map, in order, e.g. ["A", "7"].',
}

# Back-compat alias for the old skeleton name.
INSTRUCTIONS = PROMPT_TEMPLATE


def format_instructions(task: dict) -> str:
    at = task.get("answer_type", "label")
    text = FORMAT_TEXT.get(at, FORMAT_TEXT["label"])
    if at == "multiple_choice" and task.get("options") \
            and not all(str(o) in task["question"] for o in task["options"]):
        # The question does not list the options itself: append them in letter order.
        opts = "\n".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(task["options"]))
        text = f"choose one of these options:\n{opts}\nGive the answer as the single letter of the correct option."
    return text


def build_prompt(task: dict) -> str:
    return PROMPT_TEMPLATE.format(question=task["question"].strip(), format_instructions=format_instructions(task))
