# A standalone child returns its Session Result; a coordinator host keeps ownership

`@fradser/pi-subagents` spawns a Work Session and gets its settled output back into the Leader's session on its own, without `@fradser/pi-agent-teams` installed. When a coordinator host is published, the host keeps ownership of delivery and the execution layer stays silent.

## Context

The `agent` tool's description promises "Results arrive automatically: continue your own work or end the turn rather than polling, sleeping, or repeatedly inspecting a child to learn what was already delivered." Only the team runtime kept that promise. Its published host owns the spawn and delivers reports, and its worker extension registers the tools a child needs to send one. The standalone path passed no `onUpdate`, so the child's settled text was discarded at the moment it existed, and the description shipped a promise the standalone install could not keep.

The gap survived review because every exercised configuration had a coordinator in it, and the packages' own split ADR treats the layers as separately installable and separately complete. A user who installs only the execution layer gets a tool that accepts work and never returns it.

Three options were available. Make the standalone install refuse to spawn without a host, which would delete the package's reason for being separately installable. Make the `agent` tool await the child's answer synchronously, which turns a resident Work Session into a blocking call and defeats the resident model the spawner is built for. Or give the execution layer a delivery path of its own, shaped like the one the team runtime already uses.

## Decision

The execution layer delivers a **Session Result**: one custom message per settled turn, carrying the child's final text verbatim, rendered as one pi-kit lifecycle row, sent with a `followUp` delivery and a triggered turn. A child that ends without ever producing one emits one visible message that starts no turn. A published host suppresses execution-layer delivery, so installing both packages delivers each result once.

The new vocabulary term is `Session Result`, owned by the execution layer. It is not a Submission, which the glossary binds to a Task and an Assignment Attempt that a standalone spawn has neither of; not a Message, which the team runtime owns; and not Agent Presence, which reports state and carries no result.

A tool's execution context exposes no `sendMessage`, so delivery necessarily originates in the extension entry that holds the `ExtensionAPI` and arrives in the library as an injected function, on the same seam the row renderer already uses. The library stays free of the TUI and free of session reach it does not have.

## Consequences

- A delivery is now a public transcript and context contract: the custom message type, its details shape, and its provenance line are what a person's transcript and a future model will read. Changing them changes the surface, which is why the type is namespaced to the package rather than shared with the team runtime's report type.
- A resident child that settles repeatedly costs the leader a turn per settled turn. That is the price of the promise; a leader that wants a silent child has no such option, and the roster's live text remains the cheaper read.
- The visible, non-triggering ended-notice follows ADR-0002 rather than contradicting it: a death reaches the transcript as a terminal outcome, and no automatic mid-task notice is introduced. A child that dies still produces no message that asks the leader to make an ops decision.
- The execution layer now depends on session delivery, which it previously did not. A consumer that embeds the library without a delivery function gets spawning without delivery, exactly as today; the dependency is declared rather than hidden.
- With both packages installed the behaviour is unchanged from today, which is the point: the host keeps what it owned.
