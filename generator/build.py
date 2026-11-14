"""Build a task set from a spec file.

Spec (configs/*.json): {"set": "final", "tasks": [{"task_id", "family", "seed", "level", "question_type", "style"}]}

Output (tasks/<set>/):
    tasks.jsonl       one record per task: task_id, image, question, answer, answer_type, tolerance_rel|abs,
                      options, question_type, family, level, style, seed, generator_version, data, image_sha256
    images/<id>.png
    data/<id>.json    the family's data + render layout
"""


def build_set(spec_path: str, out_dir: str) -> list[dict]:
    raise NotImplementedError("TODO: loop over spec, call family.generate + family.render, write tasks.jsonl")
