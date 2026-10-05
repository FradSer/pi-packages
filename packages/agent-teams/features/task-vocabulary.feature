Feature: Task vocabulary crosses the runtime seams

  Scenario: A claimed task carries task assignment metadata
    Given a participant takes a pending task
    When its runtime assignment is read
    Then its kind is task
    And direct input still uses the direct kind
    And no retired assignment kind is declared or emitted

  Scenario: Workers receive the current task file binding
    Given the coordinator starts a worker
    When the worker resolves its environment binding
    Then it reads PI_TEAMMATE_TASKS_FILE
    And it reads tasks.json rather than a retired filename
    And the retired environment binding does not activate the worker

  Scenario: Task notices use one vocabulary
    Given an idle participant and available tasks
    When the coordinator constructs a notice
    Then the notice describes tasks and prerequisites
    And worker disclosure recognizes the task notice marker
    And no separate task container is presented as a different work type

  Scenario: The team console names its task page
    Given the team console
    When its task page is selected
    Then its page, counts, and navigation labels say tasks
    And its task detail still preserves status, dependencies, and evidence
