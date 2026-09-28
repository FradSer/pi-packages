Feature: A Work Item owns bounded context

  A Work Item is durable, so the context behind it must be too. Reassignment
  hands a successor a structured brief rather than prose or the whole history,
  and a long-lived Work Item cannot grow without limit.

  Rule: The Work Item records where it ran, not a session handle

    Scenario: A workspace path is recorded instead of a session id
      Given a Work Item that ran in an Agent workspace
      When its context is stored
      Then the workspace path is recorded
      And no session identifier appears in the Work Item
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
      When the Work Item is handed to a successor
      Then the findings are present in the brief
      And they are marked as findings the successor must not lose

    Scenario: An oversized brief is clipped and says so
      Given a handoff field larger than its share of the budget
      When the handoff is built
      Then the field is clipped to budget
      And the clipped text announces that it was clipped
      And no UTF-8 sequence is split

  Rule: Retained context is measured against a budget

    Scenario: A Work Item within budget reports so
      Given a Work Item whose description, result, handoff, and refs fit the budget
      When the context is measured
      Then it is reported as within budget

    Scenario: A Work Item over budget is reported, not silently grown
      Given a Work Item whose retained context exceeds its budget
      When the context is measured
      Then it is reported as over budget
      And the measured size counts description, result, error, handoff, and refs

  Rule: Context references cannot accumulate without bound

    Scenario: Refs are de-duplicated and capped
      Given refs containing duplicates, empty ids, and more entries than the cap
      When the refs are normalized
      Then duplicates and empties are gone
      And the list is at most the cap
      And each ref keeps its kind, id, and note
