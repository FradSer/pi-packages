# Specification: Standalone Session Result delivery

## Problem Statement

`@fradser/pi-subagents` is installable and usable on its own: it registers the
`agent` tool, spawns a child, and stops it. With only that package loaded, the
child's work never reaches the main session.

The child's settled output exists in exactly one place — the spawner's
progress stream, where an `agent_settled` event becomes
`finalResponse: true` plus the child's final text, and `emitProgress` hands it
to `onUpdate`. The standalone spawn passes no `onUpdate`. The child's answer is
therefore discarded at the moment it exists, while the `agent` tool's
description promises the opposite: "Results arrive automatically: continue your
own work or end the turn rather than polling, sleeping, or repeatedly inspecting
a child to learn what was already delivered." A leader that believes that
description ends its turn believing work is in flight that nobody will ever see.

The other half of the loss is that the text is not merely undelivered, it is
unrecordable: the roster projection for `inspect` and `list` does not carry the
child's live text, and the roster is an in-memory object on `globalThis`, so a
later process in the same project has no record at all.

A coordinator package can paper over this — a team runtime that publishes a host
owns the spawn and delivers reports itself — which is exactly what happens when
`@fradser/pi-agent-teams` is installed. That is why the gap survives review: the
only configuration anybody exercises has a coordinator in it. The standalone
install is the one the package's own README and manifest advertise, and it is
the one that cannot keep the promise its tool description makes.

## Solution

A standalone child hands its settled output back to the main session as a
**Session Result**: one delivered message per settled turn, containing the
child's final text verbatim, rendered as a single lifecycle row, and delivered
so the leader's next turn sees it without polling.

When a child ends without ever producing one, the transcript shows one visible
line saying so, and nothing wakes the leader.

With a coordinator host in place, the host keeps ownership of delivery and the
execution layer stays silent, so installing the team runtime does not double
deliver.

## User Stories

1. As a leader using only `@fradser/pi-subagents`, I want a child's final answer
   to arrive in my session, so that delegating one question and ending my turn
   actually gets me the answer.
2. As a leader using only `@fradser/pi-subagents`, I want the `agent` tool's
   description to be true, so that I can plan my turn around what the tool
   promises instead of discovering the gap after waiting.
3. As a leader, I want the delivery to be one message per settled turn rather
   than one per streamed chunk, so that a long child turn does not flood my
   context.
4. As a leader with a resident child that I wake repeatedly, I want every wake's
   answer delivered, so that the child stays useful across turns rather than
   answering only the first question.
5. As a leader, I want a repeated settle of the same turn not to deliver
   twice, so that a child emitting extra `agent_settled` events cannot duplicate
   my context.
6. As a leader, I want an empty final answer not delivered, so that a child that
   settles with nothing to say does not cost me a turn.
7. As a leader, I want a child that dies without producing a result to be visible
   in the transcript, so that a silent death is not mistaken for work in flight.
8. As a leader, I want that death notice not to start a turn of its own, so that
   recoverable execution does not consume my context.
9. As a leader, I want the death notice to keep the error detail on the roster,
   so that the roster listing still explains what happened.
10. As a person reading the transcript, I want the delivery to render as one
    lifecycle row naming the child and its result, so that it looks like every
    other background event rather than a wall of child prose.
11. As a person reading the transcript, I want no session handle in the row, so
    that the readable surface stays free of runtime identifiers.
12. As a person reading the transcript, I want the child's own text preserved
    word for word, so that the reasoning behind a result is never rewritten,
    summarised, or annotated on its way back.
13. As a person reading the transcript, I want the row to say which child and
    which incarnation produced the text, so that a result with no provenance is
    still attributable.
14. As a leader, I want the delivered text to enter my model's context, so that
    I can act on it without spending a turn asking for it.
15. As a leader with the team runtime installed, I want exactly one delivery per
    result, so that installing more packages does not duplicate my context.
16. As a leader, I want `inspect` to show the child's latest text, so that a
    second visibility path exists for a result I chose not to act on.
17. As a maintainer, I want the delivery contract to be TUI-free in the library
    and bound at the extension entry, so that the headless suites can load the
    library without a rendered session.
18. As a maintainer, I want the delivery message type to be distinct from the
    team runtime's report type, so that both packages can be installed and each
    renders its own messages.

## Scenarios

Feature: A standalone child returns its result to the Leader session

  Rule: A settled turn is delivered once

    Scenario: A prompted child's answer reaches the session
      Given a child started with a prompt and no coordinator host
      When the child's turn settles with a final answer
      Then one Session Result message is delivered to the session
      And it carries the child's final text verbatim
      And it names the child, its incarnation, and the turn

    Scenario: A second settle of the same turn delivers nothing
      Given a Session Result already delivered for a child's first settled turn
      When that child settles again without a new turn
      Then no further Session Result is delivered

    Scenario: Every wake of a resident child is delivered
      Given a resident child already delivered a Session Result
      When the child is woken with a new prompt and settles again
      Then a second Session Result is delivered with that turn's text

    Scenario: A settled turn with no text is not delivered
      Given a child whose turn settles with no final text
      When the settle is observed
      Then no Session Result is delivered

  Rule: The delivered message is a lifecycle row, not a transcript dump

    Scenario: The row names the child and its result
      Given a delivered Session Result
      When the message is rendered
      Then one row states that the child reported a result
      And the row shows the result's first line
      And no session handle appears in the row

    Scenario: The result body survives expansion in full
      Given a delivered Session Result whose text is many lines
      When the message is rendered expanded
      Then every line of the child's text is present

  Rule: A child that ends without a result says so

    Scenario: A child that dies produces a visible notice and no turn
      Given a child that ends without ever settling a result
      When its exit is observed
      Then one visible message states that the child ended
      And it carries no result text
      And delivering it starts no model turn

    Scenario: A child that already reported keeps its single notice
      Given a child that delivered a Session Result
      When that child is stopped
      Then no ended notice is delivered

    Scenario: The error detail stays on the roster
      Given a child that ended with an error
      When the roster is listed
      Then the entry carries the error
      And an exact handle does not resolve to the ended incarnation

  Rule: A coordinator host keeps ownership of delivery

    Scenario: A hosted spawn delivers nothing itself
      Given a coordinator host is published
      When a child is started through it
      Then the execution layer delivers no Session Result of its own

  Rule: The delivery belongs to the loaded entry, not the library

    Scenario: The library stays free of the TUI
      Given the package library loaded in a headless process
      When its delivery contract is imported
      Then it resolves without a rendered session

    Scenario: The entry registers the renderer and the sender
      Given the package extension entry loaded
      When it registers
      Then it registers a message renderer for the Session Result type
      And it registers one for the ended-notice type

## Implementation Decisions

- **The term is `Session Result`**, owned by `@fradser/pi-subagents`. It is the
  settled output of one Work Session turn, handed to the Leader's session. It is
  deliberately not a Submission, which the glossary binds to a Task and an
  Assignment Attempt that a standalone spawn has neither of; not a Message, which
  the team runtime owns; and not Agent Presence, which reports state and carries
  no result.
- **Delivery uses the extension-injected sender seam.** A tool's execution
  context exposes no `sendMessage`, so delivery must originate from the
  extension entry, which holds the `ExtensionAPI`. The library receives an
  injected delivery function as a tool option, the same seam the row renderer
  already uses. A library consumer that supplies nothing gets no delivery, which
  keeps the library honest about what it cannot reach.
- **The message is a custom message with a `followUp` delivery and a triggered
  turn**, plus a registered message renderer painting the shared pi-kit
  lifecycle band. The result therefore appears as one row in the transcript and
  enters the model's context, matching how the team runtime delivers reports.
- **One delivery per settled turn, keyed by incarnation and turn sequence.** The
  dedupe is armed by the turn and released when the next turn begins, which is
  the same signal the roster already models as a sequence end. Deduplication
  state is per spawn, so a replacement incarnation under the same name starts
  clean. A settle carrying no text neither delivers nor arms the dedupe: a real
  child settles empty before it settles with its answer, and treating that empty
  settle as the turn's result suppresses the answer for the life of the Work
  Session.
- **A child that ends without a result emits one visible, non-triggering
  message.** The notice is a custom message with display enabled,
  `deliverAs: "nextTurn"` and an explicit `triggerTurn: false`, so a person sees
  the death in the transcript and no model turn is spent or interrupted. The
  explicit false is the load-bearing part: pi reads an *absent* `triggerTurn` as
  permission to steer the turn in flight, which is precisely the interruption
  ADR-0002 exists to prevent. A custom message does participate in the session's
  context, so the honest claim is "no turn of its own", not "no tokens"; a
  transcript-only entry would be the strict version and is a separate decision.
  The error detail remains on the roster for the listing, which is where detail
  belongs — an exact handle addresses a living incarnation by design, so an ended
  child is listed rather than inspected.
- **Delivery has one owner and one failure record.** The tool's sender is the
  only place a delivery can fail: a synchronous throw propagates to the caller,
  which records it on the roster, and the promise `sendMessage` actually returns
  is consumed so an async failure is never an unhandled rejection. A turn counts
  as answered only once the session has taken its result, so a result lost in
  delivery still leaves a later death something to announce.
- **A settled turn is not work in progress.** The roster transitions itself out
  of `starting` only once, so the tool reconciles a settled child's status to
  `idle` itself, as the coordinator path does. A leader who inspects after a
  Session Result is told the child is waiting, not working.
- **A shutdown the Leader asked for is not a death.** `action=stop` marks the
  ending as requested before the process closes, so a planned stop produces no
  notice: the stop receipt is the report, and painting `SIGTERM` on the failure
  band would report a person's own shutdown as a failure.
- **The spawner reports a settle the moment it is parsed.** Progress is
  otherwise coalesced to one frame per stdout read, and a read carrying a settle
  *and* the next turn's start would hide the settle entirely — the exact failure
  this feature removes. The edge is emitted inside the read, and the scenario
  drives the real parser rather than a hand-written frame.
- **The message body is the child's text verbatim**, preceded by a provenance
  line naming the child, its incarnation, and the turn. Structured fields live in
  the message details for the renderer. The child's words are never summarised
  or annotated on the way back.
- **Custom message types are `subagents-session-result` and
  `subagents-session-ended`**, distinct from the team runtime's report type so
  that both packages can be installed and each renders its own messages.
- **A published host suppresses execution-layer delivery.** When a coordinator
  is in place it owns the spawn and the report, and the execution layer stays
  silent rather than delivering a second copy.
- **The roster records the child's live text** on every progress frame and
  projects it in `inspect` and `list`, which gives a result a second visibility
  path and makes the delivery decision auditable from the roster. An ended
  incarnation is read through `list` rather than `inspect`, because an exact
  handle addresses a living incarnation by design.
- **Bounded content.** The delivered text reuses the spawner's existing output
  cap, and the content carries no per-chunk accumulation: one turn's text is one
  message.
- **The kickoff prompt reaches the child exactly once.** It travels as the
  spawn's own `description`, which the spawner writes to the child's control
  stream and opens the turn baseline on. Waking an already-resident child is a
  separate operation the tool does not perform, so a prompted start cannot also
  deliver the same prompt a second time.

## Testing Decisions

- **One seam: the package extension entry with a fake `ExtensionAPI`.** The
  entry is the highest public boundary that owns both halves of the feature — the
  registration of the tools and message renderers, and the sender that delivers
  a result. A test that drives `agent action=start` through the real tool with
  an injected spawn, then feeds the real progress frames the spawner emits, and
  asserts on the messages the entry sent, exercises the whole contract without
  reaching into the delivery module. Prior art: the existing `agent` tool suite
  drives the tool with an injected spawn, and the team runtime's coordination
  rows fixture drives real entries with a fake `ExtensionAPI`.
- **Delivery behaviour is asserted on what was sent**, never on internal
  counters: the message list, its content, its options, and the renderer's
  output. A test that asserted a dedupe set would break on any refactor that kept
  the behaviour.
- **The renderer is painted with a real theme and real geometry**, the same way
  the row tests in this package paint, because a row that only renders with
  identity geometry proves nothing about a real terminal.
- **The host-suppression case is asserted through the published host**, not by
  inspecting a conditional, because "does not double deliver" is only meaningful
  as an observed absence.
- Scenarios live in a feature file in this package, and every scenario above maps
  to at least one automated check.

## Out of Scope

- Task recording, acceptance, and verification gates. A standalone spawn
  deliberately records no Task, and a Session Result is not a Submission.
- Any form of Message, inbox, or peer communication; those belong to the team
  runtime.
- Agent Presence reporting, polling surfaces, and heartbeat notices.
- Progress streaming to the leader. Only a settled turn is delivered; live frames
  stay on the roster and the console.
- Delivery of anything other than a settled final answer: tool transcripts,
  thinking traces, and intermediate text.
- Any change to the team runtime's own report delivery, which already works.
- Cross-session or cross-project delivery. A delivery reaches the session that
  started the child.

## Further Notes

- The tool description's "Results arrive automatically" promise becomes true with
  this change rather than needing a hedge, so the description is left as written.
- A live session found two defects that no offline test could see, and both are
  now scenarios: a child settles empty before it settles with its answer, which
  armed the dedupe and suppressed every real result; and the standalone path
  handed the child its kickoff prompt twice, once as the spawn description and
  once through the resident-wake call, which doubled the child's work and would
  have doubled the Leader's turns. The first version of this feature passed its
  whole offline suite and delivered nothing.
- The child remains a resident process; delivery does not stop it. A one-shot
  caller still ends the child's Work Session explicitly, and a death notice is
  what a forgotten one looks like.
- The delivery path is the same shape the team runtime uses, so the transcript
  shows the same visual language whether or not a coordinator is installed.
- Waking a resident child is not this package's job: the `agent` tool has four
  actions and none of them wakes a resident, `features/tool-surface.feature` says
  the wake arrives with a board notice, and the coordinator is what sends one.
  Unhosted, a child runs its kickoff turn. The "every wake is delivered"
  scenario is therefore a property of the per-turn dedupe, and the feature file
  says so rather than claiming a journey no shipped configuration can drive.
- The library barrel does not re-export the row module, so importing this
  package as a library loads no pi-tui and no host API. The entry reaches the
  module directly, and a scenario asserts the barrel.
- Verbatim means verbatim: a child's text containing a closing envelope tag ends
  the envelope early. Fencing it would rewrite the child's words, so the risk is
  recorded in the module instead of papered over.
