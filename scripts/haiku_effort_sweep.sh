#!/usr/bin/env bash
# Reasoning-effort sweep reported in the README: Claude Haiku 5.5 on tasks/final at low, medium and high effort,
# temperature 0 (set in eval/openrouter.py build_body), max_tokens 32000. The high run is part of results/final
# (together with GPT-6 Luna); low and medium go to their own folders.
# Usage: OPENROUTER_API_KEY=... scripts/haiku_effort_sweep.sh   (or inside Docker: see README)
set -euo pipefail
MODEL=anthropic/claude-haiku-5.5
python -m eval --tasks tasks/final --out results/final --models "$MODEL,openai/gpt-6-luna" --effort high --max-tokens 32000
python -m eval --tasks tasks/final --out results/final_haiku_medium --models "$MODEL" --effort medium --max-tokens 32000
python -m eval --tasks tasks/final --out results/final_haiku_low --models "$MODEL" --effort low --max-tokens 32000
