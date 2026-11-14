"""Build a task set from a spec file.

Spec (configs/*.json): {"set": "final", "tasks": [{"task_id", "family", "seed", "level", "question_type", "style"}]}

Output (tasks/<set>/):
    tasks.jsonl       one record per task (Track 2 fields + seed, generator_version, data path, image hash, checks)
    images/<id>.png
    data/<id>.json    the family's structured data + render layout
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from generator.families import get_family


def build_task(spec: dict, out_dir: Path) -> dict:
    fam = get_family(spec["family"])
    data, q = fam.generate(spec["seed"], spec["level"], spec["question_type"], spec["style"])
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    img = out_dir / "images" / f"{spec['task_id']}.png"
    layout = fam.render(data, str(img))
    data["layout"] = layout
    data["question"] = dict(question_type=q.question_type, question=q.question, answer=q.answer,
                            answer_type=q.answer_type, meta=q.meta)
    data_path = out_dir / "data" / f"{spec['task_id']}.json"
    data_path.write_text(json.dumps(data, indent=1, default=str))
    rec = dict(task_id=spec["task_id"], image=f"images/{img.name}", question=q.question, answer=q.answer,
               answer_type=q.answer_type, question_type=q.question_type, family=spec["family"],
               level=spec["level"], style=spec["style"], seed=spec["seed"], generator_version=fam.version,
               data=f"data/{data_path.name}", image_sha256=hashlib.sha256(img.read_bytes()).hexdigest(),
               references=data.get("references", []))
    for k in ("tolerance_rel", "tolerance_abs", "options"):
        v = getattr(q, k)
        if v is not None:
            rec[k] = v
    return rec


def build_set(spec_path: str, out_dir: str) -> list[dict]:
    spec = json.loads(Path(spec_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recs = []
    for t in spec["tasks"]:
        rec = build_task(t, out)
        recs.append(rec)
        print(f"built {rec['task_id']}: {rec['question_type']} -> {rec['answer']}")
    with open(out / "tasks.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return recs
