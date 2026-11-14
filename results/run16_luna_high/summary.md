# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 6/10 | 60% | 0.0237 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 2/3 |
| min_stops | 1/2 |
| reroute_lines | 2/3 |
| transfer_station | 1/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "A", "1"] | ["J", "R", "1"] |
| t04 | wrong: 59 St-Columbus Circle | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | correct: 4 | 4 |
| t07 | wrong: ["1", "S", "7"] | ["A", "S", "7"] |
| t08 | correct: ["D", "A", "S"] | ["D", "A", "S"] |
| t09 | correct: Canal St | Canal St |
| t10 | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0237
