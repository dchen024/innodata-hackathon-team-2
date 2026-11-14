# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 3/10 | 30% | 0.0120 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 1/3 |
| min_stops | 0/2 |
| reroute_lines | 1/3 |
| transfer_station | 1/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "A", "1"] | ["J", "R", "1"] |
| t04 | correct: 34 St-Herald Sq | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | wrong: 3 | 4 |
| t07 | wrong: ["A", "E", "6", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["F", "7"] | ["D", "A", "S"] |
| t09 | wrong: Wall St | Canal St |
| t10 | wrong: ["D", "L"] | ["F", "L"] |

Total cost: $0.0120
