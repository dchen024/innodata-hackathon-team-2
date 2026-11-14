"""Evaluate every valid task with every model and write results/<set>/.

    responses.csv     columns: model, task_id, status, parsed, question_type, response, ref_answer, correct,
                      finish_reason, error   (one row per model x task)
    run_config.json   models, temperature, max_tokens, reasoning effort, prompt, timestamps, total cost
    raw/<model>/<task_id>.json   full API responses
"""
COLUMNS = ["model", "task_id", "status", "parsed", "question_type", "response", "ref_answer", "correct",
           "finish_reason", "error"]


def evaluate(task_dir: str, out_dir: str, models: list[str], max_tokens: int) -> None:
    raise NotImplementedError("TODO")
