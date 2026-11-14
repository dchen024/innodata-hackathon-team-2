"""python -m eval --tasks DIR --out DIR [--models a,b] [--max-tokens N] [--workers N] [--effort high]"""
import argparse

from .run import DEFAULT_MODELS, evaluate


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m eval", description="Evaluate OpenRouter models on a task folder.")
    p.add_argument("--tasks", required=True, help="task folder holding tasks.jsonl and images/")
    p.add_argument("--out", required=True, help="results folder (responses.csv, run_config.json, raw/, ...)")
    p.add_argument("--models", default=",".join(DEFAULT_MODELS), help="comma-separated OpenRouter model IDs")
    p.add_argument("--max-tokens", type=int, default=32000)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--effort", default="high", help="reasoning effort (default high)")
    a = p.parse_args(argv)
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    evaluate(a.tasks, a.out, models, max_tokens=a.max_tokens, workers=a.workers, effort=a.effort)


if __name__ == "__main__":
    main()
