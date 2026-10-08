Feature: Effective work gates bounded task continuation
  Rule: Only productive runnable work continues
    Scenario: A normal run performs new work
      Given a pending task with completed prerequisites or caller-held work
      And a new successful tool receipt in this run
      When Pi settles normally without pending user input
      Then Tasks appends status after the existing boundary entries
      And requests one continuation without changing the task state

    Scenario: Only metadata or a repeated read changed
      Given unfinished runnable work
      When the run only reads the same arguments and result again or edits task metadata
      Then it requests no continuation
      And a UI transcript shows waiting with the reason
      And an identical waiting snapshot is not printed again

    Scenario: Only blocked or foreign work remains
      Given blocked work, unfinished prerequisites or another holder's work
      When no task can proceed for the caller
      Then Tasks waits without a forced inspection turn, takeover or state change

    Scenario: Restored work recovers deliberately
      Given a persisted in-progress task restored as blocked
      When the caller inspects evidence and supplies a safe recovery reason
      Then it can start a new attempt after the prerequisites complete
      And verified success is recorded with evidence

    Scenario: Historical records do not cause work
      Given only completed, replaced or recordKind execution records
      When Pi settles
      Then no task continuation or passive message is added

  Rule: Pi retains control of input and cancellation
    Scenario: A competing continuation or queued input exists
      Given new successful work and a runnable task
      When input is pending or another handler already continues
      Then Tasks neither continues nor spends allowance

    Scenario: A run aborts or fails
      Given unfinished work
      When the run outcome is aborted or error or its signal is aborted
      Then Tasks does not restart the run

    Scenario: Earlier messages and edits survive
      Given earlier boundary messages and context edits
      When Tasks emits a status snapshot
      Then the earlier entries retain their order before the Tasks message

  Rule: Allowance and reminders stay bounded
    Scenario: Three productive continuations occurred
      Given new work after each automatic continuation
      When the next normal settlement occurs
      Then Tasks shows waiting with automatic continuation limit reached
      And never claims the user paused

    Scenario: Real user input renews allowance
      Given an exhausted allowance
      When a real user message arrives
      Then new effective work can earn another continuation
      And extension-generated input does not reset the allowance

    Scenario: The model reminder is bounded
      Given many tasks with long titles
      When the status message is generated
      Then model instructions stay within twenty rows and eight KiB
      And omissions direct the model to list_tasks
      And visible titles and task bodies wrap in full without expansion

    Scenario: Malformed restored data is visible
      Given saved work with missing or invalid identity
      When it is restored
      Then it uses the persisted key as blocked work and reports a notice
      And valid runnable tasks remain independently usable

    Scenario: Headless waiting preserves the final answer
      Given a session without a UI
      When the run cannot continue
      Then no passive row replaces the final assistant answer
      And productive continuation still includes model context in every mode
