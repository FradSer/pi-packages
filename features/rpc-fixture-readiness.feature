Feature: Offline RPC fixtures preserve acknowledged child startup
  Test fixtures exercise the shipping flat agent schema and RPC parser without
  replacing readiness or accepted-input promises with unconditional success.
  One verification owner runs affected tests; integration verification belongs
  to the parent session. All HOME, Pi config, credentials and child processes
  belong to disposable local test directories.

  Scenario: Independent delegations receive correlated input acknowledgements
    Given two named child sessions with distinct prompts and no shared task
    When each child parses a prompt command and returns its matching RPC response
    Then both starts finish only after input acknowledgement
    And the exact session handles address only their own incarnations
    And stopping the sessions confirms process closure

  Scenario: A standalone install starts an idle native RPC child
    Given only the subagents package is installed in an isolated Pi process
    And its selected model exists in temporary config with a loopback-only endpoint
    When the agent tool starts a named child without a prompt
    Then the real child acknowledges get_state with idle native state
    And list and inspect report the exact handle returned by start
    And stop confirms closure without a model request

  Scenario Outline: Failed readiness cannot produce a started receipt
    Given a child whose get_state response is <response>
    When the agent tool awaits native startup readiness
    Then start is refused and no successful session receipt is returned
    And the child process is closed and reaped

    Examples:
      | response                       |
      | a correlated negative response |
      | absent until timeout           |

  Scenario Outline: Unaccepted input cannot produce a started receipt
    Given a child whose prompt response is <response>
    When the agent tool starts it with a prompt
    Then start is refused rather than treating a writable pipe as acceptance
    And the child process is closed and reaped

    Examples:
      | response                       |
      | a correlated negative response |
      | absent until timeout           |

  # Requirement adopted from subagents/VISION.md and AUTHORITY.md: only a
  # user-authored disk definition declares durable identity. Test setup is that
  # authorized author, never a model-facing persistence/create/promote switch.
  Scenario Outline: A later start reuses a fixture-authored disk identity
    Given the fixture user authored a canonical <scope> agent.md in disposable storage
    And the original definition bytes and modification time were recorded before Pi starts
    When list observes it before any child starts
    Then definitions reports it as offline with scope and source and no session handle
    And discovery provisions no memory, state, workspace or project history
    When start forks context and a later start reopens that same named identity
    Then both receipts report the definition scope and source instead of persistent or sessionNote
    And both native children acknowledge idle readiness before start returns
    And list keeps current and stopped incarnation projections in agents
    And a live definition is not also listed as offline
    And both children have agent_memory and its explicit capability extension
    And project history stays under agents/<name>/projects/<slug>/session
    And the later process uses --continue with a new exact incarnation handle
    And both launch cwd and original project binding remain the test project
    And the private workspace is an ordinary scratch directory without Git metadata or isolation
    And shutdown preserves definition bytes, modification time, Memory, workspace and history

    Examples:
      | scope         |
      | user          |
      | project       |
      | project-local |

  Scenario Outline: Settlement retains one sendable exact incarnation
    Given an acknowledged <identity> child whose input arrives through the native JSONL parser
    When authoritative assistant output and agent_settled arrive
    Then inspect reports that same incarnation as idle
    And no process close or replacement occurs at settlement
    When send addresses that exact handle with the next input
    Then it waits for the matching prompt response before reporting accepted input
    And the next settled result keeps that same child idle until explicit stop

    Examples:
      | identity           |
      | session-only role  |
      | disk-defined agent |

  Scenario Outline: Removed persistence controls cannot perform side effects
    Given an isolated install with no definition or child for the requested name
    When start includes the removed <parameter> parameter as true or false
    Then the shipping schema refuses the call
    And no child or durable identity data is created

    Examples:
      | parameter  |
      | persistent |
      | memory     |
      | worktree   |

  Scenario: Scripted provider follows the installed Pi 1.0.0 type and stream contracts
    Given scenario arguments are JsonObject values and resolved result fields are checked as JSON
    When local TypeScript checks the shared provider without a package-manager shim
    Then probe execute returns the required Promise
    And assistant streams emit typed start and done events
    And a non-JSON resolved argument fails rather than being hidden behind any or JsonObject casts
    And native installs use the repository CLI cohort with isolated HOME, config and temporary directories
