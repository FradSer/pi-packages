---
"@fradser/pi-btw": minor
---

Support multi-turn conversation in `/btw` side questions. The interactive overlay now embeds an input field to submit follow-up questions directly without exiting the popup, passes conversation history to read-only child processes, aggregates token usage and cost across turns, and handles cancellation gracefully.
