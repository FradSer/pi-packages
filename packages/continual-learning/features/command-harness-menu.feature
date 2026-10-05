Feature: Compact interactive /harness menu
  Scenario: Scoped personal rules expose their actual source path
    Given a rule comes from the user configuration scoped to the current project
    When the user selects the rule in the Harness menu
    Then the details show the actual scoped configuration file

  Scenario: No-argument /harness opens a bounded rule menu in the TUI
    Given an active project Harness with a text guidance rule
    When I run /harness with a UI
    Then I can select the rule and see its complete guidance and source
    And the menu offers a natural-language rule request

  Scenario: Creating a rule lets me choose personal or global scope
    Given an active project Harness with a UI
    When I choose to create a rule and cancel before sending the request
    Then no follow-up request is sent

  Scenario: Headless no-argument /harness keeps diagnostics
    Given an active project Harness without a UI
    When I run /harness without a request
    Then bounded diagnostics are notified

  Scenario: A broken Harness exposes diagnostics without expanding the normal menu
    Given a Harness configuration with validation errors
    When I open /harness with a UI
    Then the compact menu offers bounded diagnostics
    And it does not silently hide the configuration failure

  Scenario: A large Harness is paged without dropping rules
    Given more than forty active Harness rules
    When I move to the next Harness menu page
    Then every rule is reachable by a bounded page

  Scenario: Empty natural-language input does not author a rule
    Given I opened the Harness authoring flow
    When I submit an empty input
    Then no follow-up request is sent
