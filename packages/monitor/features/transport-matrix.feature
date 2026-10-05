Feature: Monitor outcomes across native Pi delivery boundaries
  Scenario: A background monitor reports one accurate terminal outcome
    Given a native offline RPC session executes a controlled terminal contract
    When the command succeeds, fails, times out, or exits without its sentinel
    Then one correlated terminal message carries the expected outcome
    And ordinary success progress never enters the next provider context

  Scenario: Mixed and nested calls deliver results synchronously
    Given a monitor is mixed with a foreign tool or called from another tool
    When its terminal contract resolves
    Then its caller receives the expected terminal outcome
    And no duplicate custom terminal message is sent

  Scenario: Programmatic batching keeps its validation inside the script
    Given native codemode runs several monitors concurrently
    When the script verifies every status and required payload
    Then the provider receives one script summary after all monitors resolve

  Scenario: A user stops an acknowledged background monitor
    Given an RPC monitor has returned its pending acknowledgement
    When the next requested tool call stops it
    Then the stop result identifies one stopped monitor
    And no custom terminal wake is emitted
