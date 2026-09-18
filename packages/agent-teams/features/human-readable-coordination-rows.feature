Feature: Human-readable coordination rows
  The transcript shows what a person started and said, not the handles a model
  passes around. Model-facing tool content keeps exact session, Work, and
  assignment identifiers; rendered rows never print them.

  Scenario: An Agent start row names the Agent and its task
    Given the Leader delegates Work to a new Agent with a kickoff prompt
    When the agent tool row renders
    Then the collapsed row shows the Agent name and its task on one line
    And the expanded row shows the role description, the full task text, its tools, and its model
    And no session, Work, or assignment identifier appears in the row

  Scenario: Agent action rows use plain state words
    Given an Agent has a living session
    When agent delegate, inspect, and stop rows render
    Then each row leads with the Agent name and a plain state word
    And an inspect row shows the live status and current activity of that session

  Scenario: A failed Agent row explains itself without identifiers
    Given an Agent action fails with text containing a Work identifier
    When the failed agent row renders
    Then the row names the Agent and marks it failed
    And the identifier is replaced by the Work subject it names

  Scenario: Work rows show the subject instead of the identifier
    When a leader work create, assign, release, reopen, or supersede row renders
    Then the collapsed row leads with the Work subject
    And the expanded body lines carry no Work identifier

  Scenario: Message rows show one inline copy of the complete message
    Given a leader or worker sends a message longer than 2000 characters and 50 lines
    When the agent_event row is expanded
    Then it shows one paragraph starting with "[message] to @name · steered ·" and the complete message
    And the text wraps naturally to the current terminal width with its semantic line breaks preserved
    And no clipped preview or repeated message body appears

  Scenario: Expanded messages preserve literal syntax and whitespace
    Given a leader or worker message contains JSON empty strings, spaces before punctuation, and a quoted newline
    When the registered agent_event row expands
    Then the visible message retains those quotes, spaces, and semantic line breaks
    And only unsafe terminal controls and runtime handles are transformed
    And the collapsed preview still normalizes line breaks for one-line display

  Scenario: Collapsed message previews use the actual terminal width
    Given a long message to @continual-audit-close
    When the same collapsed row renders at narrow, medium, and wide terminal widths
    Then the preview grows with the available display columns instead of a fixed character cap
    And it reserves space for the complete configured expand hint when the hint and band padding fit
    And resizing the component recomputes both the preview and whether an expand hint is needed

  Scenario: Message hints describe hidden content only
    Given a short message fits the collapsed row
    When there are no additional detail notes
    Then the collapsed row has no expand hint
    When a terminal report was also recorded
    Then the collapsed row has the configured expand hint
    And expansion shows the message once followed by a single terminal report note

  Scenario: Message layout uses native display width and safe text
    Given a message containing CJK, combining characters, ANSI escapes, and runtime handles
    When either registered leader or worker agent_event surface renders
    Then every line stays within the terminal display width and runtime handles are scrubbed
    And an exact recipient route without routing metadata shows its Agent name with one @ prefix
    And expansion preserves all printable message text without injected terminal controls
    And success, pending, and failure rows retain their native lifecycle bands

  Scenario: An expansion hint wraps in a terminal too narrow to hold it
    Given a collapsed message has hidden content
    When the terminal has fewer columns than the configured hint plus band padding
    Then the hint wraps using Pi's native wrapper instead of clipping its text
    And every emitted row stays width-bounded even when the terminal cannot hold the padding

  Scenario: Worker Work rows do not print task identifiers
    Given a Worker queues a claim or submission for a board task
    When the worker work row renders
    Then the row names the task subject
    And every body line is free of identifiers
