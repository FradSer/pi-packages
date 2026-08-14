---
name: handoff
description: "Writes a portable handoff document for another agent to use. Use when the user says \"hand this off\" or needs to transfer work to a fresh session."
disable-model-invocation: true
---

Write a portable handoff document summarising the current conversation. This skill only writes the document: it does not create, fork, or seed a session. Save it to the temporary directory of the user's OS — not the current workspace. The user or a receiving agent may use the document in a later session.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

## CRITICAL: Reference, don't duplicate — and redact

Do not copy content already captured in specs, plans, ADRs, issues, commits, or diffs — reference them by path or URL instead. Redact API keys, passwords, and personally identifiable information. Save to the OS temporary directory, never the workspace.
