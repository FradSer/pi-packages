Feature: Complete supported test type inventory
  Scenario: Every catalog type is accounted for
    Given the current catalog defines resources, invocation modes, routes, placements and graph edges
    When the type coverage inventory is generated
    Then every catalog identity is mapped to an executable check
    And every public standalone capability and workflow route has a real-model case
    And omitted public entries fail the inventory check

  Scenario: Developer tasks span independent software concerns
    Given frontend accessibility, API errors, authorization, data migration, operation budgets, localization, paths and test design fixtures
    When Matt Pocock is used on each agreed task in real Pi
    Then independent immutable acceptance tests observe RED before final GREEN
    And reports distinguish output-level checks from hosted browser, database or service verification

  Scenario: Unknown fixture names cannot silently select a receipt task
    Given a case catalog names an unknown fixture
    When it is loaded
    Then it fails before model execution

  Scenario: Optimization preserves adjacent public boundaries
    Given a rendered module, lexical path utility and indexed lookup task
    When their fixes are accepted
    Then exports stay unchanged, dot-prefixed child names stay inside and strict ID equality stays unchanged
    And empty lookup requests do not read record IDs

  Scenario: The model can see actual verification evidence
    Given fixed acceptance checks produce diagnostics
    When fixture_checks runs
    Then bounded redacted stdout and stderr are visible in the tool content
    And reports separate observed failures and metrics from source-based inference

  Scenario: Teaching in an application repository preserves its code
    Given an initial teaching request with unknown learner mission
    When the teacher inspects an existing application as an example
    Then it asks the mission question and waits
    And it does not repair application code or create implementation tests without a separate implementation request

  Scenario: Exact workflow calls include terminal controls
    Given an active workflow at any legal phase
    When its state contract lists exact available calls
    Then completion and cancellation are listed separately from transition targets
    And a finished review can complete without transitioning to a procedure named complete

  Scenario: Catalog guidance provides concrete gateway calls
    Given every model-reachable capability and workflow route
    When available gateway guidance is injected
    Then each entry includes its exact mode and identifier JSON
    And schema failures require correcting the call rather than claiming the capability ran

  Scenario: Tool consumers can discover every operation at the root schema
    Given gateway and active tools have several strict operation branches
    When a provider reads their parameter schema
    Then the root is an object with the full mode or action enumeration
    And branch requirements and forbidden sibling fields remain enforced

  Scenario: Root schema hints preserve Pi v1 argument normalization
    Given the original strict tool branches and root discovery hints
    When the actual Pi v1 validator compares finite JSON values and field combinations
    Then acceptance and normalized arguments stay equivalent
    And removing nullable hints is detected as a compatibility regression

  Scenario: Candidate stdout cannot claim acceptance completion
    Given a candidate prints the completion marker and exits before assertions
    When the trusted Node TAP reporter processes its output
    Then the candidate print is a comment and does not satisfy the completion test
