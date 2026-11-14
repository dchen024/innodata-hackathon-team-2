# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 1/10 | 10% | 0.0038 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 1/3 |
| min_stops | 0/2 |
| reroute_lines | 0/3 |
| transfer_station | 0/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["C", "E", "6"] | ["A", "E", "6"] |
| t02 | wrong: ["2", "Q"] | ["4", "Q"] |
| t03 | wrong: ["F", "C"] | ["J", "R", "1"] |
| t04 | wrong: 42 St-Bryant Pk | 34 St-Herald Sq |
| t05 | wrong: 2 | 3 |
| t06 | wrong: 3 | 4 |
| t07 | wrong: ["A", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "7"] | ["D", "A", "S"] |
| t09 | wrong: Chambers St | Canal St |
| t10 | wrong: ["6", "L"] | ["F", "L"] |

Total cost: $0.0038
