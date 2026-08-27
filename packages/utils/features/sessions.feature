Feature: Cross-session awareness and directory recap
  The utils package provides multi-session awareness for Pi sessions running in
  the same directory. Sessions automatically register their status, latest goal,
  and recap. When multiple sessions exist in the same directory, other sessions
  inject directory session recap into system prompts and expose a /sessions
  command and a session recap tool for agents to query.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: Session registers state in directory registry on startup
    Given a session starting in directory "/app/my-project"
    When session_start fires
    Then the session registers its file, PID, cwd, and initial status as idle in the registry

  Scenario: Session updates goal and status on agent start
    Given an active session in "/app/my-project"
    When the user submits prompt "Implement user authentication"
    Then the session status becomes running
    And its latest goal is set to "Implement user authentication"

  Scenario: Cross-session recap is injected when other sessions exist in cwd
    Given two active sessions "Session A" and "Session B" in directory "/app/my-project"
    When Session B receives a user prompt
    Then before_agent_start injects Session A's recap and status into the system prompt
    And the injected recap text is stripped of terminal escape sequences

  Scenario: Dead session PIDs are automatically cleaned up
    Given a registered session with a PID that is no longer running
    When querying active sessions in the directory
    Then the dead session is pruned from the registry

  Scenario: Registry records from multiple writers merge into one logical session
    Given one live session process registered twice under different id conventions
    And the first record carries goal, recap, and modified files while the second is a bare glow record
    When querying active sessions in the directory
    Then each other process appears exactly once
    And the merged record keeps the newest status and the richest available goal, recap, and modified files
    And records owned by the current process are excluded even when their ids differ

  Scenario: Corrupt registry records are normalized on read
    Given a registered record whose status is an unknown string and whose pid is a numeric string
    When querying active sessions in the directory
    Then the record is read without crashing or being pruned
    And the status falls back to "exited" and the pid is coerced to a number
    And no escape sequence from the record survives into any consumer

  Scenario: /sessions command lists directory sessions
    Given a session in directory "/app/my-project"
    When the user runs /sessions
    Then details for sessions in "/app/my-project" are displayed

  Scenario: Tool list_directory_sessions returns active sessions
    Given an agent calling tool "list_directory_sessions"
    When executed
    Then it returns structured info about all active sessions in the current directory

  Scenario: Tool list_directory_sessions renders one compact transcript row
    Given an agent calling tool "list_directory_sessions"
    When Pi renders the completed tool call in the TUI
    Then the call slot renders no content of its own
    And the result delegates to the shared pi-kit lifecycle band instead of hand-built styling
    And one "[sessions] listed" row paints a full-width custom-message band with a blank band row above and below
    And expanding the result reveals a bounded block per session with status, pid, relative age, goal, recap, and recent files inside the same band
    And every displayed field is stripped of terminal escape sequences and truncated to bounded lengths

  Scenario: Failed list_directory_sessions renders one plain error line
    Given list_directory_sessions fails
    When Pi renders the failed tool result
    Then the renderer keys off the render context isError flag
    And the transcript shows one plain error line instead of a session listing
    And the model still receives the full cross-session recap as text content
