Feature: A standalone child returns its Session Result to the Leader session

  A Session Result is the settled output of one Work Session turn. Installing
  the execution layer alone must keep that promise: the child's answer reaches
  the main session once per settled turn, as one lifecycle row, with the child's
  own words. A coordinator host, when present, keeps ownership of delivery.

  Rule: A settled turn is delivered once

    Scenario: A prompted child's answer reaches the session
      Given a child started with a prompt and no coordinator host
      When the child's turn settles with a final answer
      Then one Session Result is delivered to the session
      And it carries the child's final text verbatim
      And it names the child, its incarnation, and the turn

    Scenario: A delivered result names the child as continuable
      Given a child started with a prompt and no coordinator host
      When its turn settles with a final answer
      Then the envelope names the exact session that produced the answer
      And one envelope line states the child is IDLE and takes a dependent follow-up through agent_input
      And the child's own words remain the body of the envelope
      And the envelope claims no acceptance

    Scenario: A second settle of the same turn delivers nothing
      Given a Session Result already delivered for a child's first settled turn
      When that child settles again without a new turn
      Then no further Session Result is delivered

    Scenario: A temporary child returns multiple results before an explicit stop
      Given a temporary child with no disk identity
      When it settles its first answer
      Then it remains idle and accepts next input at the same exact incarnation
      When the caller delivers a second input
      Then the second answer is delivered once with a distinct sequence number
      And no role, Memory, workspace or session history is written to disk
      And only stop or parent shutdown closes the process

    Scenario: Every wake of a resident child is delivered
      Given a resident child already delivered a Session Result
      When a further turn of that child settles with an answer
      Then a second Session Result is delivered with that turn's text
      And the two results carry different turn numbers
      And both inputs use the same exact session
      And no replacement child is spawned

    Scenario: A settle without authoritative evidence is not delivered
      Given an intermediate frame with no completed final message
      When that frame is observed
      Then neither a result nor an unanswered notice consumes the turn

    Scenario: A completed message without final text is an unanswered outcome
      Given an authoritative completed assistant message with blank final text
      When the real sequence settles
      Then one explicit unanswered follow-up is delivered instead of a blank result
      And it carries the original bytes and available final diagnostics
      And no review verdict or acceptance is fabricated

    Scenario: An empty settle does not consume the turn's one delivery
      Given a child's turn that settles with no text
      And the same turn then settles again carrying the child's answer
      When both settles are observed
      Then exactly one Session Result is delivered
      And it carries the answer, not the empty text

  Rule: The delivered message is a lifecycle row, not a transcript dump

    Scenario: The row names the child and leaves the answer to expansion
      Given a delivered Session Result
      When the message is rendered collapsed
      Then the row is one line naming the child and that it reported
      And the answer does not appear on the collapsed row
      And the row advertises expansion
      And no session handle appears in the row
      When the same message is expanded
      Then the complete answer appears exactly once, in full
      And the answer is not repeated anywhere else in the row

    Scenario: A short result contains no duplicated answer or bookkeeping
      Given the child's complete answer is 2
      When the message is rendered expanded
      Then the answer appears exactly once below the Agent headline
      And no Session Result or turn label repeats the delivery metadata
      And the model-facing envelope and original details retain the exact answer, turn and session

    Scenario: Only hidden result text makes a successful result expandable
      Given a long single-line or multiline answer
      When the message is rendered collapsed at a narrow terminal width
      Then pi-kit advertises expansion for the hidden answer text
      When the message is expanded or resized wide enough
      Then every authored line and the long tail can be read without duplicate preview/body content
      And no fixed character cap silently shortens the displayed answer

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
      And it requests no turn, so a turn in flight is never interrupted

    Scenario: A death answering a later turn is still announced
      Given a child that delivered a Session Result for one turn
      And a further turn began and was never answered
      When that child dies
      Then one visible message states that the child ended

    Scenario: A shutdown the Leader asked for is not a death
      Given a child the Leader stopped through the tool
      When the child process closes
      Then no ended notice is delivered
      And the stop receipt stands alone

    Scenario: A child that already reported keeps its single notice
      Given a child that delivered a Session Result
      When that child is stopped
      Then no ended notice is delivered

    Scenario: The error detail stays on the roster
      Given a child that ended with an error
      When the roster is listed
      Then the entry carries the error
      And an exact handle does not resolve to the ended incarnation

    Scenario: A child that answers is not listed as working
      Given a child whose turn settled
      When the roster is listed
      Then its status is idle and its live text is the answer

  Rule: A coordinator host keeps ownership of delivery

    Scenario: A hosted spawn delivers nothing itself
      Given a coordinator host is published
      When a child is started through it
      Then the execution layer delivers no Session Result of its own

  Rule: The delivery belongs to the loaded entry, not the library

    Scenario: The library stays free of the TUI
      Given the package library barrel loaded in a headless process
      When it is imported
      Then no pi-tui module is loaded by the import
      And the delivery contract resolves without a rendered session

    Scenario: A host without a renderer still receives results
      Given a host offering the tool but no message renderer
      When a child settles
      Then the tool registers and the result is still delivered

    Scenario: A host without a session API still gets a working tool
      Given a host offering no session API at all
      When a child is started
      Then the start succeeds and the result is delivered nowhere

    Scenario: A message with unreadable details says so
      Given a delivered message whose details are not a notice
      When it is rendered
      Then one row states that the message carried no details
      And no row claims a child ended

    Scenario: Malformed notice metadata is not presented as execution evidence
      Given a delivered message with a non-finite or out-of-range timestamp or turn number
      When its details are read for rendering
      Then the notice is rejected as unreadable
      And no fabricated turn or timestamp is shown

    Scenario: The entry registers the renderer and the sender
      Given the package extension entry loaded
      When it registers
      Then it registers a message renderer for the Session Result type
      And it registers one for the ended-notice type

  Rule: The kickoff prompt reaches the child once

    Scenario: A prompted start runs one turn
      Given a child started with a prompt
      When the child is handed work
      Then the prompt reaches the child exactly once

    Scenario: A settle is reported even when a chunk carries the next turn
      Given a child's output arriving with a settled turn and a new turn in one read
      When the spawner parses that output
      Then a settled frame is reported for the answered turn

  Rule: One name for a child's answer, on both surfaces

    Scenario: The transcript row names what the model was handed
      Given a settled child turn delivered as a Session Result
      When its row is rendered expanded
      Then the row names a Session Result and the turn it carries
      And the collapsed band already showed the answer's first line

    Scenario: A child's kickoff frames the tasks positively
      Given a child started with an assigned task
      When its kickoff prompt is built
      Then it says the task text is the whole assignment
      And it names no behaviour the child is asked to avoid
