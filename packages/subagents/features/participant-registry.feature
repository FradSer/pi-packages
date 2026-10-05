Feature: The roster is published, not pushed at the tasks

  `@fradser/pi-subagents` owns child processes and `@fradser/pi-tasks` owns Work.
  Neither imports the other: a process layer that named the task set's domain would
  make every execution-layer install drag the tasks along, and the tasks that
  imported a roster would own a process concept it has no business knowing.

  They meet at one published shape instead — a holder's name, incarnation, state,
  and what it holds — on `globalThis`, which is where this package already keeps
  the roster and the coordinator host. It is read at use time rather than claimed
  at load time, so the two integrate by being installed together and installation
  order stops mattering.

  The policy stays on the task set's side: the registry supplies holders, and
  `resourcesConflict` decides. A process layer that computed conflicts would own a
  rule the domain has to agree with, which is the same coupling pointing the other
  way.

  Rule: What crosses the seam is a holder, not a roster entry

    Scenario: The roster is offered as a published holder registry
      Given a roster with one living child and one stopped child
      When the participant registry is read
      Then only the living child is listed
      And each listed holder carries its name, incarnation, state, and assignment
      And no process detail the registry does not declare crosses the seam

    Scenario: The tasks's assignment reaches the roster through the seam
      Given a published participant registry
      When something hands it an assignment and a task id
      Then the roster entry records both
      And clearing the assignment removes both

    Scenario: Publishing again replaces the registry rather than stacking it
      Given a published participant registry
      When the package is reloaded and publishes again
      Then the slot holds one registry, the republished one
      And it reads the same shared roster the first one wrote to

  Rule: Nothing in this package imports the tasks

    Scenario: No module imports the task domain
      Given the package source
      When its imports are inspected
      Then no module imports @fradser/pi-tasks or a team runtime
      And what a holder holds is described structurally, in the published shape
      And the manifest declares no dependency on the tasks
