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
    And it does not use a bare /handoff command
    And it does not use the Claude /mattpocock:<name> namespace

  Scenario: Installation documentation reflects package availability
    Given the package has not had its first npm release
    When its README is inspected
    Then it does not claim that npm installation is published
    And it directs users to install from a local checkout until the first release

  Scenario: Skills collect decisions through the Pi conversation
    Given a skill needs a decision from the user
    When it presents a recommendation or alternatives
    Then it asks directly in the conversation and waits for the reply
    And it does not depend on an ask-the-user tool or a built-in Other option

  Scenario: Skills use only available Pi collaboration and session controls
    Given a skill needs an independent review context or a fresh session
    When the Pi package is inspected
    Then it conditionally uses the teammate facility or performs reviews sequentially
    And it does not instruct the Agent tool or the unsupported /clear command

  Scenario: Skills follow repository instruction and commit conventions
    Given setup must select an instruction file or a skill finishes a change
    When the Pi package is inspected
    Then AGENTS.md is preferred before CLAUDE.md
    And it directs commits through the git-agent workflow instead of raw staging or commit commands

  Scenario: Handoff writes a document without controlling sessions
    Given a user needs a portable handoff
    When they invoke /skill:handoff
    Then the skill writes only a portable Markdown document
    And it never creates, forks, or seeds a session
    And guidance that refers to /skill:handoff preserves that document-only behavior
