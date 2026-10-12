Feature: Task lifecycle states and readable task results
  Scenario: Legacy blocked and replaced work restores without lost evidence
    Given legacy recovery_hold and superseded task records
    When the store restores them
    Then only pending, in_progress, blocked, completed and cancelled are emitted
    And failure evidence, recovery notes and replacement relations remain
    And replaced work cannot be taken, completed or automatically continued

  Scenario: Every settled TUI row collapses by default
    Given long task titles, descriptions, conditions, blockers, evidence and errors
    When any tool or automatic status message renders at a narrow width
    Then the collapsed row shows only its headline and native expansion hint
    And a headline wider than the row wraps in full instead of being elided
    And every line but the last wraps at the full width
    And the hint follows the wrapped headline on its last line
    And expanding it reveals the full body without ellipses
    And completion results show the submitted evidence on expansion

  Scenario: Paginate all matching tasks
    Given forty one matching tasks
    When list_tasks reads the first and next pages
    Then all forty one tasks are accessible without duplication
    And stale or invalid cursors are explicitly refused

  Scenario: Continue only effective work
    Given an unfinished runnable task
    When new successful work settles without pending input
    Then one bounded continuation is authorized
    Given only repeated reads, task metadata edits or blocked work
    When the run settles
    Then it waits with a reason available on expansion and does not claim user pause

  Scenario: Record and recover an operational blocker
    Given pending or caller-held work
    When update_task records blocked with a reason
    Then it releases the attempt and preserves existing evidence
    When a later update resumes it with a reason
    Then it is in_progress without the active blocker
    And a successful result retains the prior failure evidence
    When completed work is reopened
    Then its state is pending and its evidence remains available

  Scenario: Abandoned work leaves the board
    Given pending or caller-held unfinished work
    When update_task records cancelled with a reason
    Then the status is cancelled and the reason is kept
    And the task no longer counts as unfinished or claimable
    And a cancelled prerequisite still blocks its dependents
    And a completed task is reopened rather than cancelled
    And reopening a cancelled task returns it to pending with the reason cleared
    And a cancellation without a reason is refused

  Scenario: Effective receipts and pending user input
    Given a successful read or write and a runnable task
    When the same tool arguments and content are repeated
    Then the repeated receipt is not new effective work
    And identical waiting reminders are suppressed
    Given new effective work
    When user input is pending or another handler continues
    Then Tasks does not request continuation or consume allowance

  Scenario: Runtime stop cleanup preserves history despite an exhausted budget
    Given a stopped holder with an in-progress task and a small or exceeded retained-text budget
    When runtime cleanup records its full diagnostic
    Then the task is blocked and the holder lease is released
    And the diagnostic and existing history are retained

  Scenario: Replaced history cannot be deleted or resumed
    Given a replaced task, including a legacy record with a missing replacement target
    When discard, take, bind, completion or resident continuation is attempted
    Then authority is refused and the historical record remains
    And unresolved replacement chains cannot become prerequisites
    And a missing replacement target is explained without displaying undefined

  Scenario: New waiting information is visible
    Given a waiting snapshot already displayed
    When the blocker or persistence notice changes without effective work
    Then a new collapsed snapshot is recorded once
    And expanding it shows the new full information
    And no continuation is requested
