# Evaluation summary

| Model | Correct | Accuracy | Cost (USD) |
|---|---|---|---|
| `anthropic/claude-haiku-5.5` | 10/12 | 83% | 0.0348 |
| `openai/gpt-6-luna` | 9/12 | 75% | 0.0229 |

## By question_type

| question_type | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` |
|---|---|---|
| count_stops | 3/3 | 3/3 |
| min_stops | 3/3 | 2/3 |
| reroute_lines | 2/3 | 3/3 |
| transfer_station | 2/3 | 1/3 |

## Per task

| task_id | `anthropic/claude-haiku-5.5` | `openai/gpt-6-luna` | reference |
|---|---|---|---|
| p1_01 | correct: 4 | wrong: 5 | 4 |
| p1_02 | correct: ["Q", "E"] | correct: ["Q", "E"] | ["Q", "E"] |
| p1_03 | wrong: Times Sq-42 St | wrong: 34 St-Herald Sq | 7 Av |
| p1_04 | correct: 2 | correct: 2 | 2 |
| p1_05 | correct: 3 | correct: 3 | 3 |
| p1_06 | correct: 4 | correct: 4 | 4 |
| p1_07 | wrong: ["7", "4"] | correct: ["7", "Q"] | ["7", "Q"] |
| p1_08 | correct: ["6", "D"] | correct: ["6", "D"] | ["6", "D"] |
| p1_09 | correct: 59 St | wrong: Lexington Av/63 St | 59 St |
| p1_10 | correct: 42 St-Bryant Pk | correct: 42 St-Bryant Pk | 42 St-Bryant Pk |
| p1_11 | correct: 2 | correct: 2 | 2 |
| p1_12 | correct: 2 | correct: 2 | 2 |

Total cost: $0.0577
