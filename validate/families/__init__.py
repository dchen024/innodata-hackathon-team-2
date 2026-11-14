"""Per-family render and answer checks. Map family name -> check(task, data, png_path) -> {name: {"passed": ...}}."""
from validate.families.subway import check as subway_check

CHECKS = {"subway": subway_check}
