# Memory Index

- `openai_teammate_api_reference.md` — OpenAI external Teammate / Workspace Agents API reference (Workspace Agents API, Files API, file search, vector stores, Threads API). Reference only, not for Pi extension usage guidance.

- `team-centric-design.md` — Agent Teams current architecture: named resident RPC teammates, shared task board with atomic self-claim, direct P2P inboxes, verify-gated completion, harness-driven wake-ups. Supersedes the deleted run-centric DAG design.
- `follow-up-queue.md` — Teammate report steering handoff: hand reports immediately to Pi's steering channel without an internal serialized follow-up queue; delivers at safe tool boundaries.
- `attempt-bound-authority.md` — Worker communication, claims, and submissions bind to the started Assignment Attempt; failed or interrupted Work is recovery-held until an explicit leader assignment, and retired nonterminal reports leave the provider projection while staying in history.
