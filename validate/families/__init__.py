"""Per-family render and answer checks. Map family name -> check function.

Each check function: check(data: dict, layout: dict, png_path: str, task: dict) -> {check_name: {"pass": bool, ...}}
Typical checks: independent re-computation of the answer, OCR of labels, pixel positions vs data,
legibility (labels found by OCR), uniqueness (no ties within tolerance).
"""
CHECKS = {}
