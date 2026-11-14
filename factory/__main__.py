"""Command line: python -m factory {build,validate,eval,reproduce,fresh} ..."""
import argparse
import json
import sys
from pathlib import Path

DEFAULT_MODELS = "anthropic/claude-haiku-5.5,openai/gpt-6-luna"


def _eval(tasks, out, models, max_tokens):
    from eval.run import evaluate
    return evaluate(tasks, out, models=models.split(","), max_tokens=max_tokens)


def main():
    ap = argparse.ArgumentParser(prog="factory", description="Transportation visual task factory (NYC subway)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a task set from a spec, then validate it")
    b.add_argument("--spec", required=True)
    b.add_argument("--out", required=True)

    v = sub.add_parser("validate", help="run all checks on a task folder")
    v.add_argument("--tasks", required=True)

    e = sub.add_parser("eval", help="evaluate models on a task folder")
    e.add_argument("--tasks", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--models", default=DEFAULT_MODELS)
    e.add_argument("--max-tokens", type=int, default=32000)

    r = sub.add_parser("reproduce", help="rebuild tasks from a spec's seeds, check they match, evaluate and score")
    r.add_argument("--spec", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--compare", default="tasks/final", help="submitted task folder to compare against")
    r.add_argument("--models", default=DEFAULT_MODELS)
    r.add_argument("--max-tokens", type=int, default=32000)
    r.add_argument("--no-eval", action="store_true")

    f = sub.add_parser("fresh", help="build, check and score one new task")
    f.add_argument("--family", default="subway")
    f.add_argument("--seed", type=int, required=True)
    f.add_argument("--level", type=int, default=3)
    f.add_argument("--question-type", default="reroute_lines")
    f.add_argument("--style", default="clean")
    f.add_argument("--out", required=True)
    f.add_argument("--models", default=DEFAULT_MODELS)
    f.add_argument("--max-tokens", type=int, default=32000)
    f.add_argument("--no-eval", action="store_true")

    a = ap.parse_args()
    from generator.build import build_set
    from validate.run import validate_set

    if a.cmd == "build":
        build_set(a.spec, a.out)
        validate_set(a.out)
    elif a.cmd == "validate":
        validate_set(a.tasks)
    elif a.cmd == "eval":
        _eval(a.tasks, a.out, a.models, a.max_tokens)
    elif a.cmd == "reproduce":
        tdir, rdir = Path(a.out) / "tasks", Path(a.out) / "results"
        build_set(a.spec, str(tdir))
        rep = validate_set(str(tdir))
        ref = Path(a.compare) / "tasks.jsonl"
        if ref.exists():
            old = {json.loads(l)["task_id"]: json.loads(l) for l in ref.read_text().splitlines() if l.strip()}
            new = {json.loads(l)["task_id"]: json.loads(l) for l in (tdir / "tasks.jsonl").read_text().splitlines()}
            diff = [t for t in new if t not in old or any(new[t][k] != old[t].get(k) for k in
                                                          ("image_sha256", "question", "answer"))]
            print("rebuild matches submitted tasks (image hash, question, answer)" if not diff else
                  f"WARNING: rebuilt tasks differ from {ref}: {diff}")
        if not all(v["valid"] for v in rep.values()):
            print("WARNING: some rebuilt tasks failed validation", file=sys.stderr)
        if not a.no_eval:
            _eval(str(tdir), str(rdir), a.models, a.max_tokens)
    elif a.cmd == "fresh":
        out = Path(a.out)
        spec = dict(set="fresh", tasks=[dict(task_id=f"fresh_{a.family}_{a.seed}", family=a.family, seed=a.seed,
                                             level=a.level, question_type=a.question_type, style=a.style)])
        out.mkdir(parents=True, exist_ok=True)
        (out / "spec.json").write_text(json.dumps(spec, indent=1))
        build_set(str(out / "spec.json"), str(out / "tasks"))
        validate_set(str(out / "tasks"))
        if not a.no_eval:
            _eval(str(out / "tasks"), str(out / "results"), a.models, a.max_tokens)


if __name__ == "__main__":
    main()
