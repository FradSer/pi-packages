Feature: Independent Work Sessions behind compact Agent delegation
  A Leader delegates through agent and communicates through agent_event
  without managing process reuse or sending completion bookkeeping prompts.

  Scenario: New work for the same Agent has independent Work Sessions
    Given an Agent definition named reviewer
    When the Leader delegates two prompts to reviewer without a work ID
    Then both delegations start distinct Work Items and Work Sessions
    And neither prompt is sent as guidance to the other Work Session
    And inspecting reviewer lists both work IDs and precise message routes
    And inspection starts no process or model turn

  Scenario: A work ID selects exactly one Work Session
    Given reviewer has two active Work Sessions
    When the Leader sends guidance with the first work ID
    Then only that Work Session receives the guidance
    And a work ID belonging to another Agent is rejected without side effects
    And a completed work ID can explicitly start a new attempt without reusing old completion evidence
    And inspected work created through the resident entry point has the same stable handle guarantee

  Scenario: Explicit work control accounts for a pending final result
    Given a Work Session has written its final result but the Leader has not drained it
    When the Leader sends a new prompt with that work ID
    Then the recorded result is applied before choosing steering or reopening
    And the next assignment cannot be stranded behind the old completion
    And a backlog larger than one report-read batch does not hide the terminal result

  Scenario: New work uses fresh context by default
    Given the Leader has conversation history
    When the Leader delegates without fork or with fork false
    Then the new Work Session receives its own assignment without the Leader's history
    And the Agent definition and effective tool grant are preserved

  Scenario: Fork copies the active conversation context into a new Work Session
    Given the Leader has branched and compacted conversation history
    When the Leader delegates with fork true
    Then the new Work Session inherits the active context snapshot rather than a generated handoff summary
    And message roles and complete tool exchanges are preserved
    And an unfinished parent tool exchange is not replayed as child work
    And the parent history and active branch remain unchanged
    And subsequent parent and child messages do not share mutable history
    And the snapshot does not copy extension runtime identity or grant parent-only tools

  Scenario: Invalid fork controls fail before starting work
    When fork is supplied with a work ID or without a prompt
    Then delegation rejects without starting or steering a Work Session
    And an unavailable fork context fails explicitly instead of silently starting fresh

  Scenario: Runtime delivers an ordinary final answer automatically
    Given an Agent is executing a direct Work Item
    When it answers without manually sending a terminal agent_event
    And Pi confirms that execution has settled
    Then the runtime records and delivers the final answer exactly once for the current assignment
    And the Work Item is finished without a finalization reminder
    And the Leader's model-visible result identifies its work, assignment attempt, and terminal status
    And a large intermediate-report backlog does not produce a false finalization reminder
    And the Work Session remains available for explicitly directed further work

  Scenario: A large final answer remains retrievable
    Given an Agent produces a final answer larger than the report channel limit
    When execution settles
    Then the runtime delivers a bounded result with a full-result file reference
    And the complete answer remains private and retrievable until runtime cleanup

  Scenario: Execution failure is not successful completion
    Given an Agent has emitted intermediate assistant text
    When its final response fails or is aborted and execution settles
    Then the runtime delivers a failed result with the failure reason
    And it does not report the intermediate text as a successful final answer

  Scenario: Intermediate progress and retries do not finish work
    Given an Agent is executing a Work Item
    When an assistant tool call, low-level run ending, or retry occurs
    Then the Work Item remains active until execution settles
    And an explicit terminal report is not delivered twice by automatic completion

  Scenario: Completion evidence belongs to one attempt
    Given an Agent completed one assignment and starts another
    When old report events or repeated settlement events arrive
    Then they cannot complete the current assignment
    And each assignment has its own single finished announcement

  Scenario: Concurrent Agent communication requires an exact route
    Given reviewer has two live Work Sessions
    When a participant addresses reviewer by the ambiguous Agent name
    Then the message is rejected with the available precise routes
    When a participant uses one of those routes
    Then only the selected Work Session receives the message

  Scenario: A resident name cannot shadow an ambiguous Agent name
    Given a resident named reviewer and another Work Session both use Agent reviewer
    When a participant addresses reviewer without a route prefix
    Then the message is rejected as ambiguous
    And both recipients have distinct explicit session routes
    When the participant uses session:reviewer
    Then only that resident receives the message
    And the same precise routes and ambiguity checks apply to the resident send_message control

  Scenario: Forked context belongs to the Work Session lifecycle
    Given a fresh or forked Work Session has been created
    When startup fails or its owning session is shut down
    Then its temporary context files are cleaned up
    And no parent session file is removed or modified
