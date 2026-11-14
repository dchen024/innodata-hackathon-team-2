# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 2/10 | 20% | 0.0044 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 1/3 |
| min_stops | 0/2 |
| reroute_lines | 1/3 |
| transfer_station | 0/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "1"] | ["J", "R", "1"] |
| t04 | wrong: 57 St-7 Av | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | wrong: 6 | 4 |
| t07 | wrong: ["A", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["F", "N", "7"] | ["D", "A", "S"] |
| t09 | wrong: Chambers St | Canal St |
| t10 | wrong: ["6", "L"] | ["F", "L"] |

Total cost: $0.0044
