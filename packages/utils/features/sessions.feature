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

  Scenario: Dead session PIDs are automatically cleaned up
    Given a registered session with a PID that is no longer running
    When querying active sessions in the directory
    Then the dead session is pruned from the registry

  Scenario: /sessions command lists directory sessions
    Given a session in directory "/app/my-project"
    When the user runs /sessions
    Then details for sessions in "/app/my-project" are displayed

  Scenario: Tool list_directory_sessions returns active sessions
    Given an agent calling tool "list_directory_sessions"
    When executed
    Then it returns structured info about all active sessions in the current directory
