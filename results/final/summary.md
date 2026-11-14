# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 5/10 | 50% | 0.0366 |
| `openai/gpt-6-luna` | 8/10 | 80% | 0.0250 |

## By question_type

| question_type | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` |
|---|---|---|
| accessible_route | 1/3 | 3/3 |
| min_stops | 0/2 | 1/2 |
| reroute_lines | 2/3 | 3/3 |
| transfer_station | 2/2 | 1/2 |

## Per task

| task_id | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` | reference |
|---|---|---|---|
| t01 | correct: ["A", "E", "6"] | correct: ["A", "E", "6"] | ["A", "E", "6"] |
| t02 | correct: ["4", "Q"] | correct: ["4", "Q"] | ["4", "Q"] |
| t03 | correct: ["J", "R", "1"] | correct: ["J", "R", "1"] | ["J", "R", "1"] |
| t04 | correct: 34 St-Herald Sq | correct: 34 St-Herald Sq | 34 St-Herald Sq |
| t05 | wrong: 2 | wrong: 1 | 3 |
| t06 | wrong: 5 | correct: 4 | 4 |
| t07 | wrong: ["1", "S", "7"] | correct: ["A", "S", "7"] | ["A", "S", "7"] |
| t08 | wrong: ["D", "E", "6"] | correct: ["D", "A", "S"] | ["D", "A", "S"] |
| t09 | correct: Canal St | wrong: Chambers St | Canal St |
| t10 | wrong: ["6", "L"] | correct: ["F", "L"] | ["F", "L"] |

Total cost: $0.0617
