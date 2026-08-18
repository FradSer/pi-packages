Feature: /init repository guidelines command
  The utils package exposes a pi-native /init command that asks the agent to
  create or update scoped AGENTS.md contributor guides for the current repository.

  Background:
    Given the pi-utils package is installed

  Scenario: /init asks the agent to inspect the repository before writing
    When the user runs /init
    Then the command sends an instruction to inspect the repository structure,
      commands, tests, style, history, and existing instruction files
    And the instruction asks for a concise "Repository Guidelines" document

  Scenario: /init updates an existing current-directory guide safely
    Given ./AGENTS.md already exists
    When the user runs /init
    Then the instruction tells the agent to preserve useful guidance and update
      the existing document in place instead of replacing it blindly

  Scenario: /init keeps nested guides consistent with their parent scope
    Given AGENTS.md files exist in the repository root and nested directories
    When the user runs /init
    Then the instruction tells the agent to discover all scoped guides
    And update only guides relevant to the repository changes
    And explain parent-child scope relationships without duplicating content

  Scenario: /init accepts optional focus from the user
    When the user runs /init focus on package release commands
    Then the additional focus is included in the instruction sent to the agent
