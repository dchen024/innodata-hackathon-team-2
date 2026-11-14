# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 7/10 | 70% | 0.0135 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 2/3 |
| min_stops | 0/2 |
| reroute_lines | 3/3 |
| transfer_station | 2/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | correct: ["J", "R", "1"] | ["J", "R", "1"] |
| t04 | correct: 34 St-Herald Sq | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | wrong: 3 | 4 |
| t07 | wrong: ["1", "S", "7"] | ["A", "S", "7"] |
| t08 | correct: ["D", "A", "S"] | ["D", "A", "S"] |
| t09 | correct: Canal St | Canal St |
| t10 | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0135
