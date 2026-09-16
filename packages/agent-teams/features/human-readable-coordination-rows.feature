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

  Scenario: Message rows show the message text
    When a leader or worker agent_event row renders
    Then the row names the recipient Agent
    And the expanded body shows the message the sender typed

  Scenario: Worker Work rows do not print task identifiers
    Given a Worker queues a claim or submission for a board task
    When the worker work row renders
    Then the row names the task subject
    And every body line is free of identifiers
