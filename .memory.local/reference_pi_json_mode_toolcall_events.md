---
name: pi-json-mode-toolcall-events
description: pi --print --mode json streams tool activity as message_update toolcall_start/delta/end subtypes — there are NO tool_execution_start/end events; tool name only arrives at toolcall_end, arguments stream as JSON deltas
type: reference
---

`pi --print --mode json` worker streams do not emit `tool_execution_start`/`tool_execution_end` events. Tool activity is carried inside `message_update` events as `assistantMessageEvent` subtypes: `toolcall_start` (no name), `toolcall_delta` (fragments of the JSON arguments), `toolcall_end` (with the full `toolCall: { name, arguments }`). Reasoning streams as `thinking_start`/`thinking_delta`/`thinking_end`, assistant text as `text_start`/`text_delta`/`text_end`, and the final turn summary arrives in `message_end` (role assistant, `stopReason`, `content[]`, `usage`).

**Why:**
The agent-teams widget showed only "working..." during runs because `applyWorkerJsonLine` listened for `tool_execution_start/end` — events that do not exist in pi's JSON mode (verified against a live `pi --print --mode json` stream: only `turn_start`, `session`, `agent_start`, `message_start`, `message_update` with `toolcall_*`/`thinking_*`/`text_*` subtypes, `message_end`). The tool name only becomes known at `toolcall_end`, so mid-execution labels must be extracted from the accumulating `toolcall_delta` JSON (e.g. bash `command` → `bash: echo hello`, `path` → `file: main.ts`, teammate_message `subject` → `message: <subject>`).

**How to apply:**
1. Stream-parse `message_update` + `assistantMessageEvent.type`: `toolcall_start` clears state, `toolcall_delta` accumulates `delta` and retries JSON.parse for a readable label (incomplete JSON mid-stream is expected — retry on the next delta), `toolcall_end` sets the final tool name from `toolCall.name`.
2. Accumulate `thinking_delta` into a separate `liveThinking` buffer for display while no tool runs (thinking is the most reliable "what is the worker doing" signal when the model is reasoning rather than emitting text).
3. A worker that completes its final response but is not SIGTERM'd by a leader exits with code 1 naturally — `isCompletedWorkerExit(reportedCompleted=true)` accepts a SIGTERM close (cooperative shutdown via `requestReportedWorkerShutdown`), so exit 1 without coordination is expected, not a worker failure.
4. Reference implementation: `packages/agent-teams/src/spawner.ts` (`applyWorkerJsonLine`, `toolcallLabel`, `WorkerStreamState`).

**Related:** [[pi-cli-print-json-usage]] [[teammate-autonomous-and-tui]]
