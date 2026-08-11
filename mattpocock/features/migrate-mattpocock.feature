Feature: Native Pi Matt Pocock package
  Adapt the registered Matt Pocock engineering and productivity skills
  from the Claude plugin layout into a native Pi package without carrying
  Claude-only packaging or invocation assumptions.

  Scenario: Package exposes the registered skills
    Given the source Matt Pocock plugin has 27 registered skills
    When the Pi package is inspected
    Then its manifest exposes the engineering and productivity skill trees
    And every registered skill has a SKILL.md file

  Scenario: Package keeps supporting references and scripts
    Given a registered skill has references, templates, or helper scripts
    When the skill is copied into the Pi package
    Then those supporting files remain beside the skill
    And their relative links resolve from the copied skill directory

  Scenario: Package uses native Pi metadata
    Given the package is installed by Pi
    When its package manifest is parsed
    Then it contains the pi-package keyword
    And it declares skill paths under the pi field
    And it does not require a Claude plugin manifest

  Scenario: Claude-only invocation artifacts are not shipped
    Given the source contains Claude-specific agent metadata
    When the Pi package is inspected
    Then it contains no openai.yaml files
    And skill frontmatter contains no Claude-only fields
    And skill instructions do not depend on CLAUDE_PLUGIN_ROOT

  Scenario: Cross-skill references use Pi skill invocation
    Given one Matt Pocock skill refers to another Matt Pocock skill
    When the package is inspected
    Then the reference uses /skill:<name>
    And it does not use the Claude /mattpocock:<name> namespace
