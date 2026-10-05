Feature: Real model invocations through Pi 1.0
  The production extension is loaded by the actual Pi CLI in an isolated toy project.

  Scenario: A model invokes every model-callable standalone capability in the case matrix
    Given a fresh toy receipt project and immutable acceptance checks
    When the configured real model receives a task requiring a catalog capability
    Then it calls matt_pocock_workflow itself with that capability
    And its next model context contains the requested procedure source
    And its output satisfies the case's artifact or pending-question contract
    And file access and executable checks remain confined to the toy project

  Scenario: A user invokes every user-only standalone capability in the case matrix
    Given a fresh toy project and a literal matt-pocock slash command
    When native Pi command dispatch delivers the procedure to the real model
    Then the requested source appears in the actual model context
    And the model produces the requested artifact or asks the required next question
    And a standalone procedure does not activate workflow-only tools

  Scenario: The real model runs every workflow entry in the case matrix
    Given a fresh toy project and one of the five literal route commands
    When Pi dispatches the command and the real model continues the procedure
    Then the active route and initial procedure match the catalog
    And required human decisions remain pending until a supplied fixture reply
    And only a case with verified completed work may report completion

  Scenario: Natural language reaches the real routing tool
    Given an inactive workflow in a fresh toy project
    When a user asks matt-pocock to handle an ambiguous task without naming a route
    Then the real model invokes the gateway routing mode
    And no completed-work claim is inferred merely from a successful CLI exit

  Scenario: Tool guidance disambiguates modes and literal recommendations
    Given the real model receives the registered gateway and decision schemas
    When it selects a standalone capability or copies a recommended option
    Then guidance supplies the exact gateway JSON shapes
    And recommended is an exact copy of an offered option including annotations
    And a mismatched recommendation remains rejected
