Feature: Real Pi intent tool contracts
  Scenario: Native verification ignores ambient credentials and a global Pi installation
    Given the developer shell contains provider credentials and Node startup options
    And a different global Pi is available on PATH
    When the native print and TUI fixture prepares its parent process
    Then it uses the repository Pi 1.0.0 cohort
    And the parent inherits only PATH and its generated temporary configuration
    And ambient credentials, proxies and Node startup hooks are absent

  Scenario: A fresh host limits the tool selection
    Given real Pi starts with only agent_list selected
    When the subagent extension restores the fresh session
    Then agent_list remains selected and callable
    And no other intent control or loader is added

  Scenario: The host selects the complete intent family
    Given real Pi selects all five intent operations
    When the extension restores startup with or without subagents_enable
    Then all selected intent operations remain active and callable
    And a selected loader activates no additional child tool

  Scenario: A native stop returns a rejected control
    Given a configured fixture reaches the final parent marker
    When its exact-session stop is rejected
    Then the evidence records the error before any fixture assertion
    And the E2E check rejects that run even if parent shutdown closes the child

  Scenario: A caller queues input on a configured package
    Given Pi loads subagents through settings and its manifest
    When the parent creates a child and sends dependent next input
    Then the five intent tools are the selected family
    And native correlated RPC accepts both inputs in one exact incarnation
    And both final answers retain their input IDs
    And stop closes the child without private temporary data

  Scenario: Native steering retains one input sequence
    Given the configured child streams its first response
    When agent_input delivers steer guidance
    Then native RPC accepts the steer for the same input ID
    And only the final guided response returns as one result
    And no next input or replacement child is created

  Scenario: Stop retires accepted next input before it starts
    Given a prompted child still works and next input waits
    When the parent stops that exact child
    Then the next input has one cancellation notice
    And its prompt never reaches the provider
    And retained inspection remains available without control authority
