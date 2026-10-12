Feature: /autoname model-generated session name
  The utils package exposes a pi-native /autoname command that names the current
  session from what the session is about. Pi's own /name command is built into
  the interactive mode and cannot be replaced by an extension, so /autoname is
  the model-generated counterpart rather than a silent input argument.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: /autoname names the session from the session itself
    Given a session whose first request is about a flaky git worktree redirect
    When the user runs /autoname
    Then setSessionName receives one short name derived from that session
    And a confirmation reports the name that was applied

  Scenario: An optional argument steers the generated name
    When the user runs /autoname release notes rewrite
    Then the request to the model includes "release notes rewrite"
    And setSessionName receives the model's name

  Scenario: The session digest stays bounded and drops noise
    Given a session with many requests, tool results, and an assistant answer
    When the digest for the name request is built
    Then only user requests contribute text
    And the digest stays within its character budget

  Scenario: A model answer is reduced to a plain display name
    Given the model answers a quoted, multi-line name with trailing punctuation
    When the answer is cleaned
    Then quoting, markdown, and line breaks are gone
    And a name longer than the display limit is cut at a word boundary

  Scenario: A reasoning model still names the session
    Given a model that reasons before it answers and shares one token budget
    When the user runs /autoname
    Then the name request asks for no reasoning
    And the name request budgets room for reasoning plus the answer
    And setSessionName receives the name the model produced

  Scenario: A thinking-only answer names its own cause
    Given a model that spends the whole answer on reasoning
    When /autoname finishes
    Then setSessionName is not called
    And the error says the model spent its answer on reasoning

  Scenario: The name request asks for a subject, not a restatement
    When the user runs /autoname
    Then the request forbids a leading verb such as Fix
    And the request forbids naming the project even though the digest carries it
    And the request shows one good name against one bad name

  Scenario: A refused or empty model answer sets no name
    Given the model answers with only punctuation and whitespace
    When /autoname finishes
    Then setSessionName is not called
    And an error explains that no name could be generated

  Scenario: Generation always settles
    Given the provider never answers, or the session is aborted first
    When /autoname waits for the name
    Then it returns without a name instead of hanging

  Scenario: A deadline and a caller abort report different causes
    Given a provider that ignores its abort signal
    When the 20 second deadline expires
    Then the error says name generation timed out
    When the caller aborts the run instead
    Then the error says name generation was cancelled
    And the abort reports itself instead of waiting for the deadline

  Scenario: Missing model or credentials fail closed
    Given the session has no current model, or the model has no credentials
    When the user runs /autoname
    Then setSessionName is not called
    And an error names the missing prerequisite

  Scenario: Session name notifications use the shared Pi-kit notification adapter
    Given /autoname needs to report success or a failure
    When it notifies the user
    Then it delegates notification sanitization and delivery to pi-kit