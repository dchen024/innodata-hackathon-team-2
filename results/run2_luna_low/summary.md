# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 4/10 | 40% | 0.0046 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 2/3 |
| min_stops | 0/2 |
| reroute_lines | 1/3 |
| transfer_station | 1/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | wrong: ["2", "Q"] | ["4", "Q"] |
| t03 | wrong: ["F", "6", "1"] | ["J", "R", "1"] |
| t04 | wrong: 57 St-7 Av | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | wrong: 5 | 4 |
| t07 | correct: ["A", "S", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "7"] | ["D", "A", "S"] |
| t09 | correct: Canal St | Canal St |
| t10 | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0046
