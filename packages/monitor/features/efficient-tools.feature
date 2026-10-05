Feature: Compact monitor guidance with explicit finite completion
  Scenario: Finite completion is available at the registered tool boundary
    Given a caller selects completion exit for a finite workflow
    When an unterminated success prefix is later invalidated
    Then the tool waits for process exit and returns result_missing
    And its parameter schema accepts match and exit but rejects unknown modes

  Scenario: Guidance retains the choices needed for accurate low-token use
    Given the extension contributes its guidance and tool descriptions
    When Pi constructs the provider context
    Then short low-output commands still use bash directly
    And finite monitors recommend exit completion and a final newline sentinel
    And untrusted output, parse errors and truncated captures remain explicit
    And related monitors can be batched with codemode

  Scenario: Fixed descriptions avoid repeating schema mechanics
    Given tool schemas and prompt guidance contribute to every request
    When Pi constructs the context
    Then pattern mechanics are described once with the tool
    And authority, integrity, business validation and delivery choices remain in the bounded prompt

  Scenario: Injected guidance chooses execution paths without losing required information
    Given monitor guidance is included in the agent system prompt
    When related commands are planned
    Then small commands prefer grouped bash
    And monitor contracts prefer compact replies and codemode batching
    And only independent jobs use Promise.all while dependencies run in sequence
    And batches retain required payloads and failure details rather than counts alone
    And deadlines, business validation and untrusted-output authority remain explicit

  Scenario: Optional execution capabilities are checked on every turn
    Given codemode is unavailable or inactive in the current host
    When monitor guidance is injected
    Then codemode and Promise.all are not recommended
    And available bash grouping or direct monitor calls provide the fallback
    When the host enables or disables codemode between turns
    Then guidance follows the current tool selection without changing it
