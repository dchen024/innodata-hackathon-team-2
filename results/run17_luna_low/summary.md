# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 5/10 | 50% | 0.0048 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 2/3 |
| min_stops | 1/2 |
| reroute_lines | 0/3 |
| transfer_station | 2/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | wrong: ["2", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "A", "1"] | ["J", "R", "1"] |
| t04 | correct: 34 St-Herald Sq | 34 St-Herald Sq |
| t05 | correct: 3 | 3 |
| t06 | wrong: 5 | 4 |
| t07 | correct: ["A", "S", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "7"] | ["D", "A", "S"] |
| t09 | correct: Canal St | Canal St |
| t10 | wrong: ["6", "L"] | ["F", "L"] |

Total cost: $0.0048
