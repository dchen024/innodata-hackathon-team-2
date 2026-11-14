"""The exact prompt sent to the models (saved into run_config.json)."""
INSTRUCTIONS = (
    "Answer the question about the image. Think it through, then end your reply with a final line of the form\n"
    "FINAL ANSWER: <answer>\n"
)


def build_prompt(task: dict) -> str:
    raise NotImplementedError("TODO: question + answer-format instructions per answer_type")
