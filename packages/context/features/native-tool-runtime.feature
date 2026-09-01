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

  Scenario: The injected guidance routes natural-language requests to the tools
    Given the context package is installed in Pi
    When the user asks the agent to search or look up external content
    Then the injected guidance directs proactive use of context_exa for web search
    And the injected guidance directs proactive use of context_context7 for library API questions
    And the injected guidance directs proactive use of context_deepwiki for public GitHub repositories

  Scenario: The injected guidance states Exa works without a credential
    Given the context package is installed in Pi
    When the guidance is injected into the system prompt
    Then it states context_exa works without an API key via the public Exa endpoint
    And it notes EXA_API_KEY upgrades Exa to the full REST API

  Scenario: The /context workflow is one collapsible transcript message
    Given the context package is installed in Pi
    When I run /context react --method=context7
    Then Pi receives the complete workflow instruction as one custom follow-up message and starts the research turn
    And the command waits for that research turn to settle before returning
    And the collapsed transcript row identifies the requested target and method
    And expanding that row reveals the complete workflow instruction

  Scenario: Native context tools use the shared lifecycle transcript
    Given a context native tool returns retrieved documentation or search results
    When Pi renders its tool row
    Then the tool call slot is empty
    And the result is rendered through pi-kit's lifecycle result renderer
    And the collapsed row identifies the retrieval target without rendering result text
    And expanding the row reveals the bounded retrieved text

  Scenario: A /context workflow completes without stale extension contexts
    Given the context package is installed alongside the live Pi package configuration
    When I run /context react --method=context7 in Pi print mode
    Then the research turn calls context_context7
    And no extension reports a stale session context error

  Scenario: Native retrieval tools use compact expandable lifecycle transcript rows
    Given the context package is installed in Pi
    When the agent calls context_deepwiki, context_context7, or context_exa
    Then its default tool-call transcript is replaced with an empty custom call surface
    And its result is rendered as a compact context lifecycle row
    And expanding that row reveals a safe bounded rendering of the retrieval result

  Scenario: An in-flight provider lookup is cancelled by Pi
    Given a context lookup is waiting for an HTTP response
    When Pi aborts the tool execution signal
    Then the HTTP request is aborted
    And the tool execution fails rather than returning cancellation as a successful text result

  Scenario: A retrieval provider is unreachable
    Given a context HTTP request fails before receiving a response
    When the associated native tool runs
    Then the tool execution fails so Pi records an error result

  Scenario: Exa search works without a credential
    Given EXA_API_KEY is not configured
    When context_exa runs
    Then it queries the public keyless Exa endpoint at mcp.exa.ai
    And it returns search results without asking for a credential

  Scenario: An Exa credential upgrades to the full REST API
    Given EXA_API_KEY is configured
    When context_exa runs
    Then it queries api.exa.ai with the key
    And it returns full-text search results

  Scenario: A provider request exceeds its timeout
    Given a context HTTP request has no Pi execution signal
    When the configured request timeout elapses
    Then the request signal is aborted

