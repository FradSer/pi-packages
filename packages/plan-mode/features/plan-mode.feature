Feature: Minimal read-only subagent planning
  Scenario: A single plan command starts one minimal child agent
    Given the user is in a Pi session
    When the user enters /plan followed by a prompt
    Then pi-kit starts one minimal Pi child with only read, grep, find and ls
    And no planning turn is sent to the parent session
    And only the host writes the returned non-empty plan to its assigned file
    And project writes, mutating bash, and extension tools remain blocked

  Scenario: Interactive start waits for the first planning prompt
    Given the user enters /plan start or selects Start plan mode
    When the first ordinary planning prompt completes a non-empty plan
    Then the native implementation selector opens after the agent settles

  Scenario: A ready plan waits for explicit implementation consent
    Given the subagent completes its plan
    When Pi shows its native TUI selector
    Then the user can implement in the current session or a new session
    And waiting does not choose an action automatically
    And dismissing the selector keeps plan mode read-only
    And an unrelated follow-up does not repeatedly reopen review

  Scenario: Headless planning awaits the child
    Given /plan receives a prompt in print mode
    When the command completes
    Then the child has finished and its plan is saved without implementation

  Scenario: Failed or empty planning is visible without a TUI
    Given an existing saved plan and a headless planning command
    When the child fails or returns no plan
    Then stderr explains the failure
    And the existing plan remains unchanged with no implementation

  Scenario: Obsolete planners cannot publish results
    Given a planning child is running
    When the user exits, replaces the request, or changes sessions
    Then the child is aborted
    And its late result cannot write the plan or open review

  Scenario: Implement in the current session
    Given the implementation selector is open
    When the user selects Implement in current session
    Then plan mode exits and the original model is restored
    And only the current session receives the plan implementation request

  Scenario: Implement in a new session
    Given the implementation selector is open
    When the user selects Implement in new session
    Then a new session linked to the original receives the plan content and path
    And the new session starts outside plan mode
    And the original session receives no implementation request
    And unavailable or cancelled session creation never falls back to implementing here

  Scenario Outline: Review cannot outlive the plan it belongs to
    Given review opened through <entrypoint>
    When the user <transition>
    Then the native selector is aborted
    And a late choice cannot implement the obsolete plan
    Examples:
      | entrypoint | transition |
      | automatic completion | exits plan mode |
      | automatic completion | starts a new session |
      | automatic completion | replaces the planning request |
      | /plan review | exits plan mode |
      | /plan review | starts a new session |
      | /plan review | replaces the planning request |

Feature: Stable plan files and model configuration
  Scenario: Plan paths survive session transitions without overwriting files
    Given the first planning prompt reserves a bounded Unicode topic filename
    When the session is reloaded or resumed
    Then the exact plan-mode-path session entry is restored
    And another session using the same topic gets a numeric collision suffix
    And an empty reservation does not open review
    And legacy hash-named files remain untouched

  Scenario: Configure a dedicated planning model
    Given the provider and model are registered
    When /plan model provider/model is handled
    Then configuration is saved without invoking the agent or allocating a plan
    And invalid model arguments do not start planning

  Scenario: Repeated entry preserves the original model
    Given plan mode has switched to a dedicated model
    When the user enters plan mode again and later exits
    Then the model from before the first entry is restored

Feature: Read-only enforcement
  Scenario: Discussion is not execution consent
    Given plan mode is active
    When a user negates, quotes, or asks about executing a plan
    Then project writes remain blocked
    And extension-generated input cannot authorize leaving plan mode

  Scenario: Only genuine built-in tools can be allowed
    Given other extensions are loaded
    When a custom tool or an override of a built-in name is requested
    Then the tool is blocked before execution
    And genuine read, grep, find and ls remain usable
    And genuine write and edit can target only the assigned plan file

  Scenario: Safe composed shell commands support exploration
    Given plan mode is active
    When every stage of a bash chain or pipeline is read-only
    Then the command is allowed
    And quoted spaces and literal operators are preserved

  Scenario: One unsafe shell stage blocks the whole request
    Given plan mode is active
    When any stage uses mutation, execution options, substitution or redirection
    Then the entire request is blocked
    And malformed syntax and mutating Git commands are blocked
