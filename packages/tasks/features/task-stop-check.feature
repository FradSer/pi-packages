Feature: The harness checks unfinished tasks before the model stops

  Task status is not proof that the work is done. The harness returns unfinished
  tasks to model context before settlement. It does not complete tasks itself.

  Rule: The next model request receives the current task state

    Scenario: The model stops after setting a task to in progress
      Given the current session holds an in-progress task
      When the model finishes a normal response
      Then the harness appends a task status message to model context
      And it requests one continuation to perform the unfinished work
      And it does not change the task status

    Scenario: Dependencies select which tasks can proceed
      Given an unfinished task with an unfinished dependency
      And an independent pending task
      When the model attempts to stop
      Then the message identifies the unfinished dependency
      And it directs the model to available work without resource tags

    Scenario: The claimable hint names exactly what the store will let a caller take
      Given a restored pending task that still names a holder who is gone
      When the model attempts to stop
      Then the message reports that task as claimable
      And list_tasks filtered by claimable returns the same task

    Scenario: No unfinished task needs a reminder
      Given every task is completed or superseded
      When the model finishes
      Then the harness appends no task status message
      And it requests no continuation

  Rule: A reminder does not override cancellation or pending input

    Scenario: The run was cancelled or failed
      Given unfinished tasks
      When the run ends with an aborted or error outcome
      Then the harness requests no continuation
      And it does not change task status

    Scenario: Another continuation or input is pending
      Given unfinished tasks
      When another handler already requests continuation or input is queued
      Then the task check requests no additional continuation
      And it does not consume its reminder allowance

    Scenario: A blocked snapshot earns one continuation and no second round
      Given no unfinished task can immediately proceed in this session
      When the model attempts to stop
      Then the harness requests one continuation for that task snapshot
      And the status row names the blocker in its waiting reason
      And the harness does not clear a hold or transfer ownership itself

    Scenario: An unchanged blocker does not create an automatic retry loop
      Given the model has inspected the blocked task snapshot
      And no task state changes
      When the model attempts to stop again
      Then the harness reports the specific waiting reason without another continuation

    Scenario: Interrupted work can resume after inspection
      Given a restored task under a recovery hold
      When the model inspects the recorded state and confirms recovery is safe
      Then it supplies a recovery reason and starts a new attempt
      And it performs and verifies the work before marking the task completed

  Rule: The task check composes with other boundary handlers

    Scenario: Earlier boundary entries are preserved
      Given an earlier handler supplies a message and a context edit
      When the task check adds its status message
      Then all earlier entries remain in their original order
      And the task message follows them

    Scenario: A malformed task identity cannot hide valid unfinished work
      Given a saved task with a missing or non-string id
      And a valid pending task
      When the tasks are restored
      Then the malformed identity uses its persisted task key under a recovery hold
      And a notice reports the repair
      And the valid task still receives its continuation

  Rule: Repeated premature settlement is bounded

    Scenario: Available work receives no repeated continuation without progress
      Given a task continuation has returned available work to the model
      And the model reports that it needs input or authorization without changing task state
      When the model attempts to stop again
      Then the harness reports no task progress without another continuation
      And it does not exhaust the continuation allowance or change the task

    Scenario: Timestamp-only changes do not renew continuation
      Given a task snapshot was already returned for continuation
      When a repeated content update changes only its timestamp
      Then the harness requests no additional continuation for that snapshot

    Scenario: Progressing task state still has a continuation limit
      Given unfinished tasks whose state changes after each continuation
      When the model repeatedly attempts to stop without completing them
      Then no more than three task continuations run for that user input
      And the final message reports unfinished tasks and the exhausted allowance

    Scenario: New user input starts a new allowance
      Given the task reminder allowance is exhausted
      When a real user message arrives
      Then another unfinished task check can request continuation
      And a task reminder does not reset the allowance

    Scenario: Status rows follow the task display language
      Given unfinished tasks with declared dependencies
      When the harness renders its status message
      Then the row uses tasks and a status action such as continue, waiting, or paused
      And its expansion shows a bounded task summary with dependency ids and unfinished prerequisites
      And each summary line names the work once, so a derived id never repeats its own subject
      And full continuation instructions remain in model context instead of the transcript

    Scenario: Task summaries stay bounded
      Given many tasks with long subjects
      When the harness creates a reminder
      Then its model content is bounded and identifies omitted tasks
      And its transcript renderer uses a compact lifecycle row

  Rule: The passive notice exists only where a transcript can show it

    Scenario: A headless run that ends with unfinished work still prints
      Given a session with no UI and unfinished tasks
      And the current task snapshot was already returned once
      When the model finishes a normal response
      Then the task check returns no result on that settlement
      And the run prints its final assistant text
      And unfinished work that can still proceed keeps its status message in every mode
