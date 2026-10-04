Feature: Monitor outcomes in goal completion evidence
  Scenario: A pending monitor is not completed work
    Given a recorded monitor_start call
    When it returns a running acknowledgement without a terminal result
    Then it contributes no successful completion observation

  Scenario: Headless terminal status determines the observation
    Given a successful tool transport containing a terminal monitor result
    When the result status is success, failure, timeout, result_missing, or stopped
    Then evidence records success, failure, failure, failure, or reported respectively
    And an erroneous tool transport can never count as success

  Scenario: Custom results preserve terminal failures and uncertain state
    Given a monitor-result message with untrusted success claims in its text
    When its structured status is timeout or result_missing
    Then evidence records failure
    And stopped, running, unknown, or missing status only records reported

  Scenario: Monitor identity avoids duplicate observations
    Given a pending acknowledgement and repeated terminals for the same monitorId
    When completion evidence is collected
    Then only the latest terminal observation for that identity is retained
    And other monitor identities and legacy results without identity stay independent

  Scenario: Stopping a monitor is a control action
    Given a monitor_stop call
    When it succeeds
    Then evidence reports the control action without declaring command success

  Scenario: Historical counter identities are not globally unique
    Given an old failed monitor_1 result before a monitor manager restart
    When a new successful monitor_1 result follows it
    Then both terminal observations remain in evidence
    And only modern unique identities can correlate duplicate terminal delivery

  Scenario: A repeated terminal keeps its latest chronological position
    Given seventeen modern monitor identities have terminal success observations
    When the first identity delivers a later failure terminal
    Then the bounded evidence includes that latest failure as its last observation
    And only fifteen earlier successful observations remain

  Scenario: Append-only context edits preserve evidence provenance
    Given monitor custom or direct terminal observations and their recorded calls
    When a later context edit omits an observation or its assistant call
    Then omitted observations do not reach the completion check
    And replacing content preserves original roles, identity, and terminal status
    And the last direct edit wins while editing an edit cannot change its effect
