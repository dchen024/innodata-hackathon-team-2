#!/usr/bin/env bash
# Repeat the full effort sweep (both models x low/medium/high) for runs FIRST..LAST into results/run<N>_<model>_<effort>.
# Same settings as run 1: temperature 0 sent, max_tokens 32000, tasks/final. Run 1 is results/final + results/final_*.
# Usage: OPENROUTER_API_KEY=... scripts/repeat_runs.sh 4 10
set -euo pipefail
FIRST=${1:-2}; LAST=${2:-10}
for N in $(seq "$FIRST" "$LAST"); do
  for M in haiku luna; do
    ID=$([ "$M" = haiku ] && echo anthropic/claude-haiku-5.5 || echo openai/gpt-6-luna)
    for E in low medium high; do
      python -m eval --tasks tasks/final --out "results/run${N}_${M}_${E}" --models "$ID" --effort "$E" --max-tokens 32000 --workers 5
    done
  done
done
