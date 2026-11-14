# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `openai/gpt-6-luna` | 2/10 | 20% | 0.0040 |

## By question_type

| question_type | `openai/gpt-6-luna` |
|---|---|
| accessible_route | 0/3 |
| min_stops | 1/2 |
| reroute_lines | 1/3 |
| transfer_station | 0/2 |

## Per task

| task_id | `openai/gpt-6-luna` | reference |
|---|---|---|
| t01 | wrong: ["1", "E", "6"] | ["A", "E", "6"] |
| t02 | wrong: ["2", "Q"] | ["4", "Q"] |
| t03 | wrong: ["F", "A", "1"] | ["J", "R", "1"] |
| t04 | wrong: Grand Central-42 St | 34 St-Herald Sq |
| t05 | wrong: 1 | 3 |
| t06 | correct: 4 | 4 |
| t07 | wrong: ["E", "6", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "7"] | ["D", "A", "S"] |
| t09 | wrong: Chambers St | Canal St |
| t10 | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0040
