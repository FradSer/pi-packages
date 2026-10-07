Feature: Distinguish deadline and forwarding effects on the same large original input
  Scenario: Freeze the complete original request before sending
    Given a parent-valid original candidate and seventeen frozen evidence entries
    When direct and forwarded routes run with five- and fifteen-second deadlines
    Then every arm uses the same runtime, SDK, candidate and three exact request bodies
    And all original counter windows remain complete
    And only the four predetermined arms can run once
    And no candidate is applied

  Scenario: Keep credentials and raw evidence private
    Given an existing environment credential and an ephemeral forwarding token
    When a route starts
    Then direct requests target the official endpoint
    And forwarded requests target only the owned loopback proxy
    And credentials are never written to input files or public results
    And observations contain numeric judgments and hashes without original text

  Scenario: Preserve timeout and partial evidence
    Given a timed-out owned evaluation process
    When the runner stops it
    Then its process group is terminated and partial output retained privately
    And incomplete responses and missing billable usage remain unknown
    And original failed arms are not retried or relabeled
    And a transport result cannot establish semantic gold or overall quality
