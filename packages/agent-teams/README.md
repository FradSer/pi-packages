# @fradser/pi-agent-teams

Agent Teams provides one final coordination surface for Pi:

```text
agent
work
agent_event
/agent-teams
```

`agent` manages Agent sessions through strict actions:

```ts
agent({ action: "delegate", name: "reviewer", prompt: "Audit authentication" })
agent({ action: "start", name: "reviewer" })
agent({ action: "inspect", name: "reviewer", session: "session:reviewer-...:spawn-..." })
agent({ action: "stop", session: "session:reviewer-...:spawn-..." })
```

A delegate action can include an inline definition. It is session-local unless
`persist: true` is explicitly supplied in that definition.

`work` owns Work lifecycle. Leaders create/list/assign/release/reopen completed
Work/supersede; Workers list/claim/submit/release their current Work.

```ts
work({ action: "create", subject: "Fix storage", resources: ["firmware/storage"] })
work({ action: "assign", id: "fix-storage", target: { session: "session:worker-...:spawn-..." } })
work({ action: "claim" })
work({ action: "submit", outcome: "success", result: "Verification evidence" })
```

`agent_event` is communication-only. It accepts a message, a recipient or bound
reply route, and optional `inform`/`request` intent. Work lifecycle authority is
never inferred from message text.

```ts
agent_event({ to: "session:reviewer-...:spawn-...", message: "The policy changed", intent: "inform" })
```

Automatic final answers and explicit Work submission use the same Work
acceptance pipeline. Verification freezes execution and retains deferred mail as
Work history. Exact session handles are incarnation-bound, so a stale handle
cannot stop or inspect a replacement resident. Work persists for later inspection,
but a different session file does not import another session's tasks automatically.

## Install

```bash
pi install npm:@fradser/pi-agent-teams
```

Run `/reload` after installation. `/agent-teams` is the human management
surface for Presence, Work, diagnostics, and exact-session stop controls.
