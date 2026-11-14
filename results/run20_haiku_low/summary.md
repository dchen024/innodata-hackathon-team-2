# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 3/10 | 30% | 0.0169 |

## By question_type

| question_type | `anthropic/claude-haiku-5.5` |
|---|---|
| accessible_route | 0/3 |
| min_stops | 1/2 |
| reroute_lines | 1/3 |
| transfer_station | 1/2 |

## Per task

| task_id | `anthropic/claude-haiku-5.5` | reference |
|---|---|---|
| t01 | wrong: ["D", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "A", "2", "1"] | ["J", "R", "1"] |
| t04 | correct: 34 St-Herald Sq | 34 St-Herald Sq |
| t05 | wrong: 2 | 3 |
| t06 | correct: 4 | 4 |
| t07 | wrong: ["1", "S", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["F", "6"] | ["D", "A", "S"] |
| t09 | wrong: Chambers St | Canal St |
| t10 | wrong: ["6", "L"] | ["F", "L"] |

Total cost: $0.0169
