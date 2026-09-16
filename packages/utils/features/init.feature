Feature: /init repository guidelines command
  The utils package exposes a pi-native /init command that asks the agent to
  create or update scoped AGENTS.md contributor guides for the current repository.

  Background:
    Given the pi-utils package is installed

  Scenario: /init asks the agent to inspect the repository before writing
    When the user runs /init
    Then the command sends an instruction to read repository evidence as needed
      for the guidance being audited rather than requiring a full repository tour
    And the instruction asks for a concise "Repository Guidelines" document
    And the instruction derives tooling and shared-library conventions from the
      target repository's own files and documentation

  Scenario: /init prunes instructions instead of filling a template
    Given existing guidance contains generic advice and mandatory reading lists
    When the user runs /init
    Then the instruction asks for removal of stale, redundant, and overprescriptive rules
    And replaces mandatory reading lists with task-specific documentation pointers
    And imposes no word quota or mandatory section checklist

  Scenario: /init defines evidence-based autonomy and completion
    Given the repository documents local workflow safety and approval boundaries
    When the user runs /init
    Then the instruction preserves genuine safety boundaries
    And permits verified safe local work without repeated approval
    And defines completion and stopping conditions without prescribing needless tests
    And keeps guidance useful across models without model-specific claims

  Scenario: /init uses progressive disclosure without expanding its editing scope
    Given repository skills are relevant to contributor guidance
    When the user runs /init
    Then the instruction recommends short precise triggers and task-specific references
    And skill files are not edited unless explicitly requested

  Scenario: /init stays neutral about the target repository's technology stack
    Given the target repository uses its own languages, tools, and shared modules
    When the user runs /init
    Then the instruction contains no hardcoded package names, dependency syntax,
      or policies from the utils package's development repository
    And it does not prescribe host-specific instruction-loading behavior
    And it asks the agent to omit conventions that repository evidence does not support

  Scenario: /init works without Git metadata
    Given the starting directory is not a Git checkout
    When the user runs /init
    Then the instruction uses that directory as the project root
    And it omits unavailable git history instead of inventing commit conventions

  Scenario: /init updates an existing current-directory guide safely
    Given ./AGENTS.md already exists
    When the user runs /init
    Then the instruction tells the agent to preserve useful guidance and update
      the existing document in place instead of replacing it blindly

  Scenario: /init treats nested guides as independent scopes
    Given AGENTS.md files exist in the repository root and nested directories
    When the user runs /init
    Then the instruction tells the agent to discover all scoped guides
    And update only guides relevant to each directory
    And avoid adding inheritance references or duplicating parent instructions

  Scenario: /init accepts optional focus from the user
    When the user runs /init focus on package release commands
    Then the additional focus is included in the instruction sent to the agent

  Scenario: /init follow-up status uses the shared Pi-kit notification adapter
    Given the agent is busy when the user runs /init
    When the command queues the guide task as a follow-up
    Then its user notification delegates sanitization and delivery to pi-kit

  Scenario: /init leaves line wrapping to the Pi TUI
    When the user runs /init
    Then the instruction sent to the agent keeps paragraph and bullet line breaks
    And the instruction does not contain source-code indentation or blank-line noise
    And the instruction does not insert manual blank lines to impose a text width
    And the TUI wraps each line to fit the screen
