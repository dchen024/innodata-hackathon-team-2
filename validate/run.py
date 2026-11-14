"""Run all checks on a task folder; write <task_dir>/checks.json and set `checks` / `valid` on each record."""
from __future__ import annotations

import json
from pathlib import Path

from validate.families import CHECKS
from validate.schema import check_record


def validate_set(task_dir: str) -> dict:
    d = Path(task_dir)
    recs = [json.loads(l) for l in (d / "tasks.jsonl").read_text().splitlines() if l.strip()]
    report = {}
    for rec in recs:
        res = check_record(rec, d)
        fam_check = CHECKS.get(rec.get("family"))
        if fam_check and res["schema"]["passed"]:
            data = json.loads((d / rec["data"]).read_text())
            res.update(fam_check(rec, data, str(d / rec["image"])))
        failed = [k for k, v in res.items() if v.get("passed") is False]
        rec["checks"] = {k: v.get("passed") for k, v in res.items()}
        rec["valid"] = not failed
        report[rec["task_id"]] = dict(valid=not failed, failed=failed, details=res)
        print(f"{rec['task_id']}: {'VALID' if not failed else 'INVALID ' + ', '.join(failed)}")
    (d / "checks.json").write_text(json.dumps(report, indent=1, default=str))
    with open(d / "tasks.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return report
