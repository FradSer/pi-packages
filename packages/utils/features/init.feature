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
    And the instruction says to prefer pi-kit for shared reusable logic when available

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

  Scenario: /init preserves meaningful prompt structure
    When the user runs /init
    Then the instruction sent to the agent keeps paragraph and bullet line breaks
    And the instruction does not contain source-code indentation or blank-line noise
    And the TUI wraps each line to fit the screen
