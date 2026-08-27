# Memory Index

- `openai_teammate_api_reference.md` — OpenAI external Teammate / Workspace Agents API reference (Workspace Agents API, Files API, file search, vector stores, Threads API). Reference only, not for Pi extension usage guidance.

- `team-centric-design.md` — Agent Teams current architecture: named resident RPC teammates, shared task board with atomic self-claim, direct P2P inboxes, verify-gated completion, harness-driven wake-ups. Supersedes the deleted run-centric DAG design.
- `follow-up-queue.md` — Leader-report FIFO handoff: dispatch the first report to Pi's native follow-up queue while the leader is active; native follow-up does not interrupt tool loops.
