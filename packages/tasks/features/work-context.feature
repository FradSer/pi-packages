Feature: A Task owns bounded context

  A Task is durable, so the context behind it must be too. Reassignment
  hands a successor a structured brief rather than prose or the whole history,
  and a long-lived Task cannot grow without limit.

  Rule: The Task records where it ran, not a session handle

    Scenario: A workspace path is recorded instead of a session id
      Given a Task that ran in an Agent workspace
      When its context is stored
      Then the workspace path is recorded
      And no session identifier appears in the Task
      And Pi resolves the session from that path, which keeps this package free of processes

  Rule: A successor receives a structured brief

    Scenario: A handoff carries the candidate, delta, checks, findings, and outstanding work
      Given an outgoing attempt that checked a candidate, changed files, ran checks, and left findings
      When the handoff is built
      Then every supplied field appears in the handoff
      And formatting it produces one section per present field
      And an absent field produces no empty section

    Scenario: Prior findings survive outside the result a reopen clears
      Given prior review findings recorded in a handoff
      When the Task is handed to a successor
      Then the findings are present in the brief
      And they are marked as findings the successor must not lose

    Scenario: A successor's brief adds to the findings already recorded
      Given a handoff holding prior findings
      When a later update supplies only its own delta
      Then the findings recorded earlier are still in the handoff
      And a findings list is added to rather than replacing the one already there

    Scenario: A note on a reference can be corrected
      Given a reference recorded with a note
      When a later update supplies a corrected note for the same reference
      Then the corrected note is the one kept

    Scenario: An oversized brief is clipped and says so
      Given a handoff field larger than its share of the budget
      When the handoff is built
      Then the field is clipped to budget
      And the clipped text announces that it was clipped
      And no UTF-8 sequence is split

  Rule: Retained context is measured against a budget

    Scenario: A Task within budget reports so
      Given a Task whose description, result, handoff, and refs fit the budget
      When the context is measured
      Then it is reported as within budget

    Scenario: A Task over budget is reported, not silently grown
      Given a Task whose retained context exceeds its budget
      When the context is measured
      Then it is reported as over budget
      And the measured size counts everything the Task retains, not only the fields the task set knows by name

    Scenario: A completion gate is measured like any other free text
      Given a Task carrying a large completion gate
      When the context is measured
      Then the gate counts against the budget
      And a Task created over budget is refused rather than written
      And the refusal names the task without quoting the input back

  Rule: What a caller stores is what the task set can account for

    Scenario: A context the task set does not recognize is refused
      Given a context carrying a field the task set has no definition for
      When it is recorded
      Then the recording is refused and says which field is unknown
      And nothing unrecognized is retained

    Scenario: A context a caller got wrong is measured, not waved through
      Given a context that a caller spelled wrongly
      When it is measured against the budget
      Then it is measured by what it carries rather than by the fields the task set happens to read

    Scenario: A budget smaller than one byte is refused
      Given a context naming a budget of less than one byte
      When it is recorded
      Then the recording is refused
      And the Task is not left with a budget no later write could satisfy

    Scenario: A budget may be tightened but never loosened past the task set's own
      Given a context naming a budget larger than the task set's default
      When it is recorded
      Then the effective budget is the task set's default
      And a budget below the default is honoured as given

    Scenario: The store refuses an unknown context field on its own account
      Given a context naming a field the task set has no definition for
      When a caller records it directly through the store
      Then the recording is refused and the field is named
      And nothing is silently dropped in its place

  Rule: Context references cannot accumulate without bound

    Scenario: Refs are de-duplicated and capped
      Given refs containing duplicates, empty ids, and more entries than the cap
      When the refs are normalized
      Then duplicates and empties are gone
      And the list is at most the cap
      And each ref keeps its kind, id, and note

    Scenario: The cap applies to what a caller stores, not only when asked
      Given a Task updated through the tool with duplicate, empty, and over-cap refs
      When the update is recorded
      Then the stored refs are de-duplicated, free of empties, and at most the cap

    Scenario: Resource tags are capped like every other retained list
      Given a Task carrying more resource tags than the cap allows
      When the tags are recorded
      Then the recording is refused
      And the tags count against the byte budget like any other free text

  Rule: A misplaced context field is corrected, not refused as unknown

    Scenario: Handoff fields at the context level move into the handoff
      Given a context carrying candidate, delta, verification, priorFindings and outstanding at the context level
      When it is recorded
      Then each of those fields is stored in the handoff
      And the call is not refused for a field the context already defines

    Scenario: A misplaced field the handoff does not own is named with its destination
      Given a context carrying a handoff field at the context level
      And a field no layer of this context owns
      When it is recorded
      Then the refusal names each misplaced field
      And the refusal says which field owns it and where it belongs

    Scenario: A moved field is not kept in both places
      Given a context carrying a handoff field at the context level
      When it is recorded and then read
      Then the handoff holds the field exactly once
      And the context level does not hold a second copy

  Rule: A validation refusal does not describe the validator

    Scenario: No model-facing text reports a schema as false
      Given any refusal this package returns to a model
      When its text is inspected
      Then it does not contain the phrase "schema is false"
      And it names the field and what the field accepts
