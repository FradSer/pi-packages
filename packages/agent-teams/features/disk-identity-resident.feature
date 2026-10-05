Feature: Team consumers honor disk identity and resident execution
  The execution contract in ../subagents/VISION.md owns identity and lifetime.
  Task acceptance and peer messages remain coordination concerns.

  Scenario: A prompted hosted start confirms input acceptance, not pipe delivery
    Given a temporary team child with a pending correlated prompt acknowledgement
    When the host receives no acknowledgement yet
    Then its start receipt remains pending even if the pipe is writable
    When native Pi acknowledges started or queued input
    Then start returns the complete exact incarnation handle
    And a handled, rejected, timed-out or closed input never reports acceptance

  Scenario: Every settled child stays idle in the same incarnation
    Given a temporary or disk-defined team child
    When it settles a result
    Then its presence is idle and its process is not stopped
    And send can continue that exact incarnation until stop or parent shutdown
    And a task result still uses the existing attempt-bound acceptance pipeline

  Scenario: Hosted send delivers two results without resetting or replacing the child
    Given a hosted temporary child has settled its first attempt
    When send addresses its same exact idle handle with another input
    Then a new attempt is published before delivery and native input acknowledgement is awaited
    And the second settled result passes through the task pipeline once
    And both results have the same incarnation and distinct attempts
    And no new process or new_session control is created

  Scenario: Hosted interrupt steers one busy sequence with native acknowledgement
    Given a hosted child is executing one attempt
    When interrupt addresses its exact handle with steering input
    Then its correlated steer acknowledgement is awaited
    And the same sequence, attempt and history produce one settled result
    And idle or stale handles cannot steer a replacement

  Scenario: Uncertain hosted input retains authority rather than claiming rejection
    Given send has reserved the next attempt before native acknowledgement
    When its acknowledgement times out
    Then no acceptance receipt is returned
    And the attempt stays held because execution may already have started
    And a second send refuses until the outcome is inspected or the process is stopped

  Scenario: Late acknowledgements cannot undo settled evidence
    Given a hosted send has already settled and delivered its attempt result
    When the pending RPC response is subsequently rejected
    Then the refusal does not erase the result or reopen its report sequence
    And a still-pending startup acknowledgement cannot authorize a sibling send

  Scenario: Verification authority is checked after draining final reports
    Given an idle child has an undrained final report with a verification gate
    When send drains that report before considering the next input
    Then the pending gate freezes the holding before any input is sent
    And no new attempt or control command bypasses verification

  Scenario: Disk scopes supply durable data without creating another identity
    Given a canonical user agent.md and same-name project and project-local overrides
    When a team child starts with that role
    Then project-local instructions outrank project and user instructions and inline input
    And every disk scope receives Memory, an ordinary scratch workspace and private project history
    And neither provisioning nor shutdown writes or promotes an agent.md
    And no Git branch, worktree, commit, preserve or release hook runs

  Scenario: Inline roles remain temporary
    Given an inline session role and the original project cwd
    When a team child starts and settles
    Then it uses that project cwd and no-session
    And it creates no private identity, workspace, memory or session directory
    And the team extension does not clear another package owner's role registry

  Scenario: Public guidance keeps the six lifecycle verbs without persistence flags
    When idle or active team guidance and role reference are read
    Then agent offers start, send, inspect, list, interrupt and stop
    And identity persistence is declared only by a user-authored disk agent.md
    And no invocation persistence, Memory opt-in, worktree or promotion option is taught
