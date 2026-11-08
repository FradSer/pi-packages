Feature: Explicit low-token Docker smoke for the subagents package
  Scenario: One pass over every functional path with the configured real model
    Given a disposable Magpie provider exposing hunyuan-eval/hy4-dev with reasoning off
    And a Docker image built from the current subagents and kit sources
    And no real upstream credential is written into the image or evidence
    When the compact study runs one child per functional path
    Then the four intent tools, parent-model selection and native TUI repaint are exercised
    And temporary, saved, restart, stale-handle and Memory capabilities retain their contracts
    And the measured provider tokens and request count are reported without quality claims
