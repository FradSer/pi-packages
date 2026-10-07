Feature: Select frozen independent projects for real learning comparison
  Scenario: Preserve historical project selection
    Given no explicit heldout cohort is requested
    When the real-project runner selects experiments
    Then only click, p-limit and mitt are selected

  Scenario: Explicit heldout cohort uses verified pristine environments
    Given the heldout cohort is explicitly requested
    When the real-project runner selects experiments
    Then only yocto-queue, humanize and referencing are selected
    And each uses its frozen upstream commit and verified original test command
    And referencing checks out the suite at the parent's frozen gitlink
    And an incompatible project and cohort fails before any inference

  Scenario: Bind cohort metadata to implementation evidence
    Given cohort metadata changes
    When the implementation digest is computed
    Then the digest changes

  Scenario: Requested main model does not inherit ambient selection
    Given the host Memory settings select another model
    When the real-project experiment creates temporary agent configuration
    Then it explicitly uses cli-proxy and opencode/deepseek-v4.1-flash
    And the host configuration is unchanged
