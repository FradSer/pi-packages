Feature: End-to-end BDD verdict
  The package reads a Gherkin .feature scenario and one run evidence file, then
  reports whether the scenario was fulfilled. Clauses with a declared check are
  decided in code. Only the remaining clauses are sent to the TypeSafe Jev model.
  Policy, gates, and the final verdict stay in code, never in the model.

  Background:
    Given the e2e package is installed
    And a scenario has Then clauses and a run evidence file

  Scenario: Deterministic checks decide the clauses that declare them
    Given a run evidence file declares a check for Then clause 1
    And that check compares an observed value against an expected value
    When the package verifies the scenario
    Then clause 1 is decided in code from the observed value
    And no question is sent to Jev for clause 1

  Scenario: Remaining clauses become narrow independent Jev questions
    Given a run evidence file declares no check for Then clause 2
    When the package verifies the scenario online
    Then clause 2 is asked as its own yes or no question
    And the scenario verdict and the business severity are asked in the same request
    And the request carries the scenario text and the run evidence as state

  Scenario: The final verdict comes from code, not from the model
    Given the model answers a verdict choice and a severity score
    When the model verdict probability is below the verdict gate
    Then the composed verdict is needs_review
    And the policy reports the gate that decided the outcome
    And a deterministic failure overrides a fulfilled model verdict

  Scenario: A clause without evidence stays unverified
    Given no check and no model answer covers a Then clause
    When the package verifies the scenario offline
    Then that clause is reported as unjudged
    And the composed verdict needs review instead of claiming fulfillment

  Scenario: The report names the verdict, the clauses, and the source of each answer
    Given a verification finished with mixed clause outcomes
    When the package renders the markdown or HTML report
    Then the report lists every Then clause with its status and its source
    And the report states how many clauses are still unjudged
    And the HTML report marks the verdict and each clause row with a stable test id

  Scenario: The CLI keeps CI exit codes stable
    Given a fulfilled scenario
    When the CLI verifies it
    Then the CLI exits with code 0
    And an unfulfilled scenario exits with code 1
    And a scenario that needs review exits with code 2

  Scenario: The pi extension exposes the same verification as a command
    Given the extension is loaded
    When the user runs /e2e with a feature and an evidence path
    Then the extension runs the same core and notifies the verdict
    And the extension never asks for or stores a model credential

  Scenario: The extension injects a stable e2e capability note directly after the system prompt
    Given the e2e extension is loaded in Pi
    When the session prepares its transcript for a provider turn
    Then the harness injects a stable capability note at index 1
    And the note teaches the model when and how to call e2e_verify

  Scenario: The extension provides an autonomous e2e_verify tool
    Given the e2e extension is loaded in Pi
    When the agent loop executes an e2e_verify tool call
    Then the tool runs the three-layer verification engine
    And the tool returns structured verdict data with clause breakdown

  Scenario: The harness gate intercepts settlement when an unfulfilled verification was recorded
    Given a scenario verification that resulted in not_fulfilled or needs_review
    When the agent attempts to settle the turn
    Then the harness gate intervenes before settlement
    And the harness returns a continuation checkpoint requiring the failure to be resolved
