Feature: Failed or aborted planner output cannot become a learning candidate
  Scenario: A failed assistant includes a valid JSON plan
    Given a planner reply contains a syntactically valid Memory, Harness or AGENTS.md plan
    And its terminal reason is error or aborted even though the CLI exits successfully
    When the parent extracts the child plan
    Then no plan is accepted from that reply
    And the failure is classified as model failure or cancellation
    And no repair, semantic judgment or application uses its partial text

  Scenario: A planner fails after emitting an earlier plan
    Given a structured plan was emitted before a terminal failure
    When the complete child transcript is inspected
    Then the earlier plan cannot escape the failed terminal state

  Scenario: The worker explicitly recovers with a successful fresh reply
    Given a failed reply is followed by a successfully completed reply
    When the successful reply supplies a valid bound plan
    Then only the recovered reply can be accepted
    And legacy structured-plan output without terminal messages remains supported

  Scenario: Retry bookkeeping follows an aborted reply
    Given a model error is followed by an aborted reply
    And Pi emits a successful retry bookkeeping event
    When no successful fresh assistant reply follows
    Then the planner remains cancelled and does not request repair

  Scenario: Failed usage is unavailable in a compatible receipt
    Given a failed attempt has no authoritative usage
    When the pipeline receipt is built or a legacy receipt is displayed
    Then missing usage and cost are unavailable rather than zero or free
    And completed attempts remain identifiable as known subtotals

  Scenario: An empty recovery cannot restore a failed-state legacy plan
    Given a legacy structured plan was emitted while the child was failed
    When a successful fresh assistant reply contains no plan
    Then the failed-state plan is not accepted

  Scenario: Incomplete planner cost keeps its known prefix without claiming a full receipt
    Given a planner completed paid replies before an error or an incomplete usage record
    When the parent records the attempt
    Then the numeric ledger retains all known usage and cost
    And the receipt does not mark the attempt usage as complete
    And only an actual matching persistent receipt excludes a ledger from additional known costs
