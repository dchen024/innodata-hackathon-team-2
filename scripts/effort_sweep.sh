#!/usr/bin/env bash
# Reasoning-effort sweep reported in the README: Claude Haiku 5.5 and GPT-6 Luna on tasks/final at low, medium and
# high effort, temperature 0 requested (eval/openrouter.py build_body), max_tokens 32000. The high runs of both models
# are the reported run in results/final; low and medium go to their own folders.
# Usage: OPENROUTER_API_KEY=... scripts/effort_sweep.sh
set -euo pipefail
H=anthropic/claude-haiku-5.5
L=openai/gpt-6-luna
python -m eval --tasks tasks/final --out results/final --models "$H,$L" --effort high --max-tokens 32000
for EFFORT in medium low; do
  python -m eval --tasks tasks/final --out "results/final_haiku_$EFFORT" --models "$H" --effort "$EFFORT" --max-tokens 32000
  python -m eval --tasks tasks/final --out "results/final_luna_$EFFORT" --models "$L" --effort "$EFFORT" --max-tokens 32000
done
