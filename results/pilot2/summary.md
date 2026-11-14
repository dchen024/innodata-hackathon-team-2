# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 8/11 | 73% | 0.0432 |
| `openai/gpt-6-luna` | 5/11 | 45% | 0.0276 |

## By question_type

| question_type | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` |
|---|---|---|
| accessible_route | 1/3 | 1/3 |
| min_stops | 3/3 | 2/3 |
| reroute_lines | 2/2 | 0/2 |
| transfer_station | 2/3 | 2/3 |

## Per task

| task_id | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` | reference |
|---|---|---|---|
| p2_01 | wrong: ["7", "Q"] | correct: ["S", "Q"] | ["S", "Q"] |
| p2_02 | correct: Chambers St | correct: Chambers St | Chambers St |
| p2_03 | correct: ["F", "7", "6"] | wrong: ["E", "6"] | ["F", "7", "6"] |
| p2_04 | correct: 6 | wrong: 5 | 6 |
| p2_05 | wrong: ["E", "D"] | wrong: ["E", "C"] | ["E", "A"] |
| p2_06 | correct: Jay St-MetroTech | wrong: Bergen St | Jay St-MetroTech |
| p2_08 | correct: 3 | correct: 3 | 3 |
| p2_09 | correct: ["D", "A", "E"] | wrong: ["F", "6"] | ["D", "A", "E"] |
| p2_10 | wrong: 42 St-Port Authority Bus Terminal | correct: Times Sq-42 St | Times Sq-42 St |
| p2_11 | correct: ["E", "6"] | wrong: ["6"] | ["E", "6"] |
| p2_12 | correct: 3 | correct: 3 | 3 |

Total cost: $0.0708
