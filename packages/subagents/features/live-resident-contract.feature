Feature: Disk identities and steering cross the real Pi resident boundary

  These checks load the production extension in Pi 1.0.0, spawn real RPC
  children and use only loopback scripted models under isolated HOME/config.

  Scenario: A user-authored disk identity resumes private history and Memory
    Given agents/name/agent.md exists with a minimal read grant
    And a previous parent Pi recorded a child history
    When another parent starts that name without lifecycle flags
    Then the child resumes projects/slug/session and reads memory/capability.md
    And a coordinator does not replace the saved identity with temporary execution
    And definition and capability bytes remain unchanged
    And native correlated input acknowledgement precedes the start receipt

  Scenario: A temporary role has no durable home and stays resident
    Given a name with no disk definition
    When it returns a result
    Then it remains IDLE until explicit stop or parent shutdown
    And no definition, Memory, workspace or session file exists

  Scenario: A project identity provisions data without writing a user definition
    Given project/.pi/agents/name/agent.md and no user identity
    When a child starts and settles
    Then its history lives in the private user data home
    And no agents/name/agent.md is created at user scope
    And the project definition is unchanged

  Scenario: Native idle readiness precedes a prompt-less receipt
    Given a disk identity started without kickoff
    When native get_state confirms idle readiness
    Then the start receipt returns and no answer is fabricated

  Scenario: Steering refuses an idle child and next input queues while it works
    Given an exact idle incarnation
    When steer input is requested
    Then it is refused and points at next delivery
    When acknowledged input opens a turn and another next input arrives while busy
    Then the busy input is queued without replacing execution

  Scenario: Steering preserves the same sequence and delivers one result
    Given a real active child with a gated loopback response
    When steer input is acknowledged queued
    Then its success receipt follows the correlated native steer acknowledgement
    And native session identity and process remain the same
    And no new_session command or second agent_start occurs
    And one agent_settled delivers the final result once

  Scenario: Native expanded details show disk identity provenance once
    Given a TUI startup receipt for a disk identity
    When native Ctrl+O expands it
    Then its source is shown once, hidden in the collapsed summary
    And rows fit the terminal and parent shutdown closes children without deleting data
