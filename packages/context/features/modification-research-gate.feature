Feature: Context package modification guidance
  To keep the single-tool package coherent
  As a maintainer of @fradser/pi-context
  I want modifications to preserve its isolated context retrieval contract

  Scenario: A runtime change preserves the child constraints
    Given a change targets the context package
    When the maintainer changes the child launcher
    Then the child remains limited to the documented read-only tool surface
    And temporary research material remains under /tmp

  Scenario: Documentation-only changes do not require unrelated lookups
    Given a change targets documentation or local tests only
    When the maintainer starts implementation
    Then the maintainer does not need external retrieval tools
