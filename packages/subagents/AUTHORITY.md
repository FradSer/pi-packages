# Authority for one subagent

`auto` permits routine local runtime work after an authorized invocation;
`confirm` requires an explicit user decision; `forbid` is unavailable under that
operation. Tools/environment allowlists are not an operating-system sandbox.

| Operation | Policy | Limits |
| --- | --- | --- |
| Select an agent tool family | auto | Authorized user/instruction delegation; activation starts no process and is availability selection, not a security authorization gate. |
| Start a temporary child | auto | Session-only role and context, minimal tools, no durable data. |
| Start an existing disk identity | auto | Definition scope supplies persistence; use private Memory/history/workspace, never replace it with an amnesiac role. |
| Create a disk identity | confirm | User authors `agent.md` or explicitly invokes a library operation. The model tools expose no persistence/create/promote switch and never calls `persistAgentDefinition`. |
| Provision durable data | auto | A valid disk identity permits shared Memory/scratch, parent/project-scoped history and atomic package-owned state. The parent ID comes from the native session or trusted runtime options. Existing project-only history stays untouched. |
| Read definitions / inspect / list | auto | Read-only facts, bounded output/errors and offline identities; no directories or model turns created by discovery. |
| Next input | auto | Exact handle and bounded FIFO reservation. Start only after current settlement and ACK; recheck the original host policy. |
| Steer active input | auto | Guide the exact active sequence; retain its input ID, with no abort or new sequence. An idle target is refused. |
| Stop / parent shutdown | auto | Record intent before closure, retain authority until confirmed, preserve data. Tool-wait cancellation does not imply stop or rejected input; dispatched exact controls continue to settle. |
| Capability Memory | auto | Present for every disk identity; absent for session roles. Append creates or replaces a same-name entry under the effective write grant; read-only execution roles may record unaccepted proposal files as an explicit exception, not append capability entries. |
| Widen existing grant | forbid | Invocation may remove tools, never add ones the definition does not grant. |
| Git workspace / automatic commit | forbid | Scratch workspace is an ordinary directory. No branch, Git worktree, commit, preserve/release hook or automatic merge. |
| Migrate legacy data | confirm | Explicit user-approved migration inventory/plan, conflict checks and provenance; copy rather than delete originals. No migration on discovery/start. |
| Delete legacy worktrees / discard output | forbid | No automatic removal; separate explicit human decision outside this migration. |
| Accept or integrate results | forbid | Execution evidence does not confer another workflow's acceptance or integration authority. |

Project definitions may specialize the same named identity while data stays in
its user-private home; provisioning that data does not promote the project role
into a user definition. A temporary agent cannot become durable by writing a
flag or by promoting its live conversation. Headless operation bypasses no
required user authorization. Labels are display text, never identity or storage selectors.
Unknown explicit identities and saved identities combined with temporary instructions
are refused before effects. Cancellation of a caller wait does not revoke an
accepted input reservation; stop and shutdown end unstarted records explicitly.

`agent_message` is standalone-only and requires an explicit effective grant; its
body is untrusted execution data. A parent message cannot supply user consent,
authorize work, claim acceptance, settle a Session Result, or retarget a child.

A persistent scratch directory provides no project checkout or write isolation.
Editing project files directly changes the user's original working tree. Shell
access can also read any files available to the operating-system user.
