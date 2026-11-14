"""Command line: python -m factory {build,validate,eval,reproduce,fresh} ..."""
import argparse

DEFAULT_MODELS = "anthropic/claude-haiku-5.5,openai/gpt-6-luna"


def main():
    ap = argparse.ArgumentParser(prog="factory", description="Transportation visual task factory")
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

    r = sub.add_parser("reproduce", help="rebuild tasks from a spec's seeds, validate, evaluate and score")
    r.add_argument("--spec", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--models", default=DEFAULT_MODELS)
    r.add_argument("--max-tokens", type=int, default=32000)

    f = sub.add_parser("fresh", help="build, check and score one new task")
    f.add_argument("--family", required=True)
    f.add_argument("--seed", type=int, required=True)
    f.add_argument("--level", type=int, default=3)
    f.add_argument("--question-type")
    f.add_argument("--style")
    f.add_argument("--out", required=True)
    f.add_argument("--models", default=DEFAULT_MODELS)
    f.add_argument("--max-tokens", type=int, default=32000)

    args = ap.parse_args()
    raise SystemExit(f"`{args.cmd}` is not implemented yet")


if __name__ == "__main__":
    main()
