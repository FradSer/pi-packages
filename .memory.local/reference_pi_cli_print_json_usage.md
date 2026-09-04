---
name: pi-cli-print-json-usage
description: pi --print --mode json emits a JSONL event stream whose message_end carries token/cost usage — parse it for child-process cost accounting
type: reference
---

`pi <cli.js> --print --mode json --no-session [--model M] [--tools T] "Task: ..."` runs a one-shot non-interactive agent and streams JSONL events to stdout. The final assistant `message_end` event carries `message.usage: { input, output, cacheRead, cacheWrite, totalTokens, cost: { total, ... } }`, and the assistant text is in `message.content[].text`.

**Why:**
Verified live while building `teammate_spawn` (packages/agent-teams): the JSON mode is the only way to get worker token/cost usage back from a spawned child Pi process. Text mode (`--print` alone) returns only the final answer.

**How to apply:**
1. Spawn workers with `--print --mode json` and parse the JSONL line-by-line: `JSON.parse` each line, keep the last `message_end` with `message.role === "assistant"`.
2. Extract text from `message.content` parts where `type === "text"`; extract usage from `message.usage` (cost total is `usage.cost.total`).
3. `resolvePiCli` must verify `process.argv[1]` is actually the pi CLI (walk up to a `package.json` with name `@earendil-works/pi-coding-agent`) — otherwise test scripts get mistaken for the CLI and the child hangs.
4. Reference implementation: `packages/agent-teams/src/spawner.ts` (`parseWorkerOutput`) + `packages/agent-teams/src/types.ts` (`WorkerUsage`).

**Related:** [[teammate-autonomous-and-tui]]
