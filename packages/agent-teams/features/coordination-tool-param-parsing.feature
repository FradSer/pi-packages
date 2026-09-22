Feature: Coordination tool parameters survive union-root schemas

  Some harnesses JSON-parse each tool parameter by name against the root schema
  `properties`. The coordination tools (`agent`, `work`, worker `work`) express
  their per-action contracts as a root Type.Union, which exposes only `anyOf`;
  object and array parameters such as `definition`, `target`, `dependsOn`,
  `resources`, and `supersedes` then reach validation as unparsed JSON strings
  and every branch rejects the call before the handler runs.

  Scenario: Union-root schemas expose structured parameters at the root
    Given the agent, work, and worker work tool schemas
    Then each root schema declares properties for every parameter used by any branch
    And object and array parameters keep their structured JSON type at the root

  Scenario: Union-root schemas declare an object type
    Given the registered agent, work, and worker work tool schemas
    When a provider requires root properties to be declared on an object type
    Then each root schema declares type "object"
    And each root schema keeps its per-action anyOf branches

  Scenario: Per-action contracts stay strict
    Given the agent tool schema
    When a delegate payload carries definition as an object
    Then the schema accepts it
    And unknown extra properties are still rejected
    And inspect without a session handle is still rejected

  Scenario: Stringified structured parameters are normalized before handlers use them
    When a harness delivers definition, target, dependsOn, resources, or supersedes as JSON strings
    Then normalization parses them back into objects and arrays
    And plain string parameters pass through untouched
