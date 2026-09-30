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

    Scenario: A second settle of the same turn delivers nothing
      Given a Session Result already delivered for a child's first settled turn
      When that child settles again without a new turn
      Then no further Session Result is delivered

    Scenario: Every wake of a resident child is delivered
      Given a resident child already delivered a Session Result
      When a further turn of that child settles with an answer
      Then a second Session Result is delivered with that turn's text
      And the two results carry different turn numbers
      # The wake itself belongs to whoever coordinates the child. With a host
      # published the host wakes it and keeps delivery; unhosted, a child runs
      # its kickoff turn. This scenario is therefore a property of the dedupe,
      # not a journey any shipped configuration can drive end to end.

    Scenario: A settled turn with no text is not delivered
      Given a child whose turn settles with no final text
      When the settle is observed
      Then no Session Result is delivered

    Scenario: An empty settle does not consume the turn's one delivery
      Given a child's turn that settles with no text
      And the same turn then settles again carrying the child's answer
      When both settles are observed
      Then exactly one Session Result is delivered
      And it carries the answer, not the empty text

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
