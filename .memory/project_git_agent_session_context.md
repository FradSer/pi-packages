---
name: git-agent-session-context
description: git-agent CLI is conversation-blind — commit intents must be built from the session record, not a one-liner
type: project
---

The git-agent commit message generator is conversation-blind by design: its only context sources are `--intent` (a string the agent passes), the staged diff, project scopes (`.git-agent/config.yml`), and co-change hints from `graph.db`. It never reads Pi/Claude session files.

**Why:**
Root-caused while optimizing the commit flow (git-agent/pi-git-agent): a one-line intent from the agent loses the session's user wording, decision rationale, and verification steps, so commit bodies record *what* changed but not *why*. Furthermore, when invoked multiple times in a session, passing the full un-deduplicated session context repeatedly creates context redundancy.

**How to apply:**
1. The `session_context` extension tool (`~/Developer/FradSer/git-agent/pi-git-agent/extensions/session-context.ts`) reads `ctx.sessionManager.getEntries()` and returns recent user messages. By default (`sinceLastCall: true`), it automatically deduplicates messages to return only new user requests since the last `session_context` call or `git-agent commit` execution.
2. Build the `--intent` from that context (2-4 sentences: what the user asked for, why the change exists, how it was verified). Never fall back to a compressed one-liner; the commit/commit-and-push procedures encode this.

**Related:** [[git-agent-commit-scope]]
