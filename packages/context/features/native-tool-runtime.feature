Feature: Native context tool behavior
  To expose only usable Pi-native interfaces and truthful retrieval failures
  As a user of @fradser/pi-context
  I want the documented command surface and tool results to match the Pi runtime

  Scenario: The README advertises the /context command rather than skills
    Given the context package is installed in Pi
    When I read its README
    Then it documents /context as the entry point
    And it may describe context-researcher only as an optional manual prompt brief
    But it does not advertise any skill path or invocable agent

  Scenario: An in-flight provider lookup is cancelled by Pi
    Given a context lookup is waiting for an HTTP response
    When Pi aborts the tool execution signal
    Then the HTTP request is aborted
    And the tool execution fails rather than returning cancellation as a successful text result

  Scenario: A retrieval provider is unreachable
    Given a context HTTP request fails before receiving a response
    When the associated native tool runs
    Then the tool execution fails so Pi records an error result

  Scenario: A required Exa credential is absent
    Given EXA_API_KEY is not configured
    When context_exa runs
    Then it returns a nonfatal message explaining how to configure the credential
    And it does not make an HTTP request

  Scenario: A provider request exceeds its timeout
    Given a context HTTP request has no Pi execution signal
    When the configured request timeout elapses
    Then the request signal is aborted

