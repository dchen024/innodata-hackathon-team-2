# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 5/10 | 50% | 0.0042 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 1/3 |
| min_stops | 1/2 |
| reroute_lines | 2/3 |
| transfer_station | 1/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | wrong: ["J", "1"] | ["J", "R", "1"] |
| t04 | wrong: 42 St-Bryant Pk | 34 St-Herald Sq |
| t05 | correct: 3 | 3 |
| t06 | wrong: 3 | 4 |
| t07 | wrong: ["A", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "7"] | ["D", "A", "S"] |
| t09 | correct: Canal St | Canal St |
| t10 | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0042
