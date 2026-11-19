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
      And it is therefore blocked with nobody holding it
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
      Then the dependent is blocked rather than left completed
      And the dependent names the task whose reopening withdrew its premise
      And its recorded gate verdict is withdrawn with it

    Scenario: A cascade reaches every conclusion, not just the nearest
      Given a chain of three completed tasks, each depending on the one before
      When the first is reopened
      Then the first task is pending and the two dependent conclusions are blocked

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
      And both dependents return to `blocked`

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

  Rule: Actual blockers have an explicit state

    Scenario: A failed attempt leaves the task in blocked state, not pending
      Given a taken task
      When the attempt reports a failure
      Then the task's status is blocked
      And its status is not pending
      And the blocker is retained as its evidence

    Scenario: New or reopened work is pending
      Given a new task or reopened completed task
      Then its status is pending
      And it is not in blocked state

    Scenario: Taking from blocked state needs a stated reason
      Given a task in blocked state
      When a caller takes it without a reason
      Then the take is refused and the refusal names the state
      And a caller that supplies a reason takes it

    Scenario: A file written before the state existed restores correctly
      Given a saved task with status pending and a legacy recoveryRequired flag set
      And a saved task that was in progress
      When the task set is restored
      Then both tasks are in blocked
      And the flag is not written back

  Rule: A creator is accountable for the work it records itself

    Scenario: A task recorded and finished by the same caller completes without a take
      Given a task recorded by this caller
      When the caller completes it with its evidence
      Then the completion is accepted
      And no take was needed, because the record already names who is accountable

    Scenario: A caller that neither took nor recorded the task is still refused
      Given a task recorded by another participant
      When this caller completes it
      Then the completion is refused for having no attempt to accept

  Rule: An honest attempt is not made to pay for the checks twice

    Scenario: Create, take and complete is three calls, and the third one is accepted
      Given a task created, taken, and worked on in this session
      When it is completed with its evidence in that one completion call
      Then the completion is accepted without a refusal
      And the whole attempt cost the three calls the state machine requires

    Scenario: A refusal names every unsatisfied check at once
      Given a task being completed with more than one check unsatisfied
      When the completion is refused
      Then the refusal names every unsatisfied check, not only the first
      And the model can satisfy all of them in the one call that follows

    Scenario: The call after a refusal succeeds, so the attempt costs at most one extra call
      Given a task whose completion was refused
      When the caller supplies everything the refusal named
      Then the completion is accepted
      And the attempt has cost at most one call more than a task set without checks

    Scenario: The checks that would refuse a first attempt are reported before it starts
      Given a task carrying a completion gate
      When it is taken
      Then the result names what a completion of this task must carry
      And an honest model can satisfy it in the completion call it was going to make anyway

