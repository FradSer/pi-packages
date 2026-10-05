Feature: A completion is checked before it is recorded

  A model splits a large task into n tasks that may depend on each other, takes
  them in parallel or in series, and then marks them complete. The task store is the
  only thing that sees the whole sequence, so it is where a completion has to be
  checked: a task marked done whose dependencies are not done, or that nobody
  ever worked on, or that carries no evidence, is a completion the task store cannot
  tell apart from real work.

  These checks belong to the store because they are facts about the tasks.
  Running a declared gate does not: a gate is a prompt, and a task set that
  evaluates a prompt is a task set that runs agents. So the tasks demands the answer
  and records it; something outside decides what the answer is.

  Rule: A completion is supported by the task set's own facts

    Scenario: A completion whose dependency is unfinished is refused
      Given a task that depends on another task
      And the other task is not completed
      When the dependent task is completed
      Then the completion is refused and names the unfinished dependency
      And the tasks never holds a completed task depending on an unfinished one

    Scenario: A success must carry evidence
      Given a task being completed successfully
      When no result is recorded
      Then the completion is refused
      And the refusal names what would satisfy it

    Scenario: A task nobody worked on cannot be accepted
      Given a task that was never taken
      When it is completed
      Then the completion is refused, because there is no attempt to accept

    Scenario: A dead holder's work can still be accepted
      Given a task whose holder reported a failure
      And it is therefore back in pending with nobody holding it
      When it is completed
      Then the completion is accepted, because the attempt is on the record

    Scenario: A declared gate must be answered
      Given a task carrying a completion gate
      When it is completed with no verdict for that gate
      Then the completion is refused
      And a verdict supplied with the completion satisfies it

  Rule: A withdrawn premise takes its conclusions with it

    Scenario: Reopening pulls back what was concluded on it
      Given a completed task that a completed task depends on
      When the dependency is reopened
      Then the dependent is back in pending rather than left completed
      And the dependent names the task whose reopening withdrew its premise
      And its recorded gate verdict is withdrawn with it

    Scenario: A cascade reaches every conclusion, not just the nearest
      Given a chain of three completed tasks, each depending on the one before
      When the first is reopened
      Then all three conclusions are back in pending

    Scenario: The withdrawal is reported, not silent
      Given a reopen that withdraws a conclusion
      When the result is read
      Then it names the tasks it pulled back
      And the evidence each one recorded is still there for the next attempt

    Scenario: A dependent being worked on is invalidated, not a refusal
      Given a task with a dependent that is being worked on right now
      When the dependency is reopened
      Then the reopen goes ahead, because it is the only way back
      And the dependent's attempt is invalidated and its lease released
      And the tasks still holds no completed task depending on an unfinished one

    Scenario: Reopen supports completed and in-progress dependents
      Given two completed tasks with separate dependent tasks
      And one dependent is completed while the other is in progress
      When each prerequisite is reopened
      Then both reopens succeed
      And both dependents return to `recovery_hold`

  Rule: A caller can ask what is blocking a completion, not only find out by failing

    Scenario: A task says which of its dependencies are unfinished
      Given a task that depends on another task
      And one of those dependencies is not completed
      When the task is read or listed
      Then it names the unfinished dependency as what blocks it
      And a task with every dependency completed names nothing

    Scenario: A list can be narrowed to what is completable right now
      Given a chain of tasks where one has been completed
      When the list is asked for tasks that could be completed now
      Then it returns exactly the ones whose dependencies are met
      And the rest are absent rather than returned and refused

  Rule: Every route into a completion is checked the same way

    Scenario: A submission through a marker is not a way around the checks
      Given a participant submitting a completion through an intent marker
      And a caller that asked for the checks
      When the submission carries no evidence
      Then it is refused, exactly as a direct call would be

    Scenario: A marker can carry the gate verdict
      Given a participant submitting a completion for a gated task
      When the marker carries a verdict
      Then the verdict is recorded like any other answer

  Rule: The checks are opt-in so a coordinator can adopt them deliberately

    Scenario: The checks are off unless a caller asks for them
      Given a caller that asks for no checks
      When a task is completed with no evidence and an unfinished dependency
      Then the completion is accepted, as it always was
      And a caller that asks for the checks gets every refusal

    Scenario: Every check is asked for on its own
      Given a caller that asks for one check only
      When a task fails exactly that check
      Then it is refused for that reason alone
      And the other checks are not applied

  Rule: Recovery hold is a state of its own

    Scenario: A failed attempt leaves the task in recovery hold, not pending
      Given a taken task
      When the attempt reports a failure
      Then the task's status is recovery_hold
      And its status is not pending
      And the blocker is retained as its evidence

    Scenario: Pending now means never attempted
      Given a task that was never taken
      Then its status is pending
      And it is not in recovery hold

    Scenario: Taking from recovery hold needs a stated reason
      Given a task in recovery hold
      When a caller takes it without a reason
      Then the take is refused and the refusal names the state
      And a caller that supplies a reason takes it

    Scenario: A file written before the state existed restores correctly
      Given a saved task with status pending and a recovery hold flag set
      And a saved task that was in progress
      When the task set is restored
      Then both tasks are in recovery_hold
      And the flag is not written back

