Feature: The task tools

  `create_task`, `get_task`, `list_tasks` and `update_task` are the whole
  model-facing surface. A tool result is what a model reads, and a row is what a
  person reads; both have to carry the same state, because a task that looks
  takeable on the row and is refused by the tool is a decision the model cannot
  act on.

  The four operations follow Claude Code's task tools. Their snake_case names
  follow this workspace. Dependency edges determine which work can proceed.

  Rule: One package, four tools

    Scenario: The extension entry registers exactly four tools
      Given the package's extension entry
      When it is loaded
      Then it registers create_task, get_task, list_tasks and update_task, and nothing else
      And it registers a default export, because the manifest points at this file
      And the removed single "task" tool is not registered under any name

    Scenario: get_task is a read and nothing else
      Given the get_task parameter schema
      When its properties are read
      Then the only property is the task id
      And a read that accepted anything else would be a write wearing a read's name

    Scenario: No tool offers a way to name who does a task
      Given the four parameter schemas
      When their properties are inspected
      Then none of them accepts a participant name or an assignee
      And a call carrying one is refused as an unknown field

  Rule: Every position is reachable exactly one way

    Scenario: update_task's status is the only route to a transition
      Given the update_task parameter schema
      When its status enum is read
      Then it is exactly in_progress, completed and pending
      And the field routes to the named store transition rather than assigning a value
      And a completion still needs an explicit outcome

    Scenario: A position outside the enum is refused by name
      Given a status this task set does not define
      When a task is updated with it
      Then the call is refused and the valid positions are named
      And it does not fall through to the content branch

  Rule: Dependencies define task order

    Scenario: The four tools do not expose resource locks
      Given the four registered task tools
      When their parameters and results are inspected
      Then no tool offers a resources parameter or a resources result field
      And a call supplying resources fails parameter validation

    Scenario: Older resource fields do not appear in the transcript
      Given a saved task with resource tags from an earlier version
      When it is read, listed, or rendered
      Then no resource tags appear in the tool result or the lifecycle row
      And its dependencies and unfinished prerequisites remain visible

    Scenario: Independent tasks can proceed while dependents wait
      Given two independent tasks and a task that depends on both
      When the independent tasks are taken and completed
      Then both can be in progress at the same time
      And the dependent cannot start until both are completed
      And no resource tags are required for any transition

  Rule: The caller is derived, never supplied

    Scenario: The main session holds the task it takes
      Given a session that published no holder binding
      When it takes a task
      Then the recorded holder is the main session

    Scenario: A participant holds the task it takes
      Given a session bound to a holder name
      When it takes a task
      Then the recorded holder is that name
      And a model cannot name a different one, because no parameter carries it
  Rule: A result says what a reader must not have to infer

    Scenario: A task in recovery hold is not presented as claimable
      Given a task whose last attempt failed
      When it is listed
      Then the result names the `recovery_hold` state
      And the reason a hold was cleared is carried when there was one

    Scenario: A task set whose file could not be read says so
      Given a durable task set that exists but cannot be read
      When the task set is listed
      Then the result carries a notice
      And the task set is not silently presented as empty

  Rule: A list is bounded by the cap the caller asked for

    Scenario: The limit a caller supplied is the limit that applies
      Given a task set holding more tasks than one result should carry
      When it is listed with a limit
      Then at most that many tasks are returned
      And the result says how many tasks the task set holds in total
      And the result says that the list was truncated

    Scenario: A cap below one task is the empty list, not a truncated lie
      Given a task set holding at least one task
      When it is listed with a limit of zero
      Then no tasks are returned
      And the result still says how many tasks the task set holds

    Scenario: A negative cap is refused rather than quietly ignored
      Given a task set holding at least one task
      When it is listed with a negative limit
      Then the call is refused and the valid range is named

    Scenario: A result is bounded whether the cap came from the model or the host
      Given a task set holding more tasks than one result should carry
      When it is listed with no limit at all
      Then the result is still bounded, because no listing is unbounded

  Rule: A programmatic caller reads data, not prose

    Scenario: The result is declared, so a caller receives it as data
      Given the tool's definition
      When its output schema is read
      Then the definition declares one
      And a successful result carries structured content naming every field it holds

    Scenario: A refusal carries its data as well as its error
      Given a call the task set refuses
      When the result is inspected
      Then it is marked as an error for the model
      And it still carries structured content, because a refusal is data too

    Scenario: The tool declares the reach it actually has
      Given the tool's annotations
      When they are read
      Then the tool declares that it does not reach beyond this machine
      And it declares that a repeated call is not the same as the first
      And it makes no claim about being non-destructive, because reopening erases a recorded result

  Rule: Name, details, dependencies, and status describe the task

    Scenario: Full task reads include the work to perform
      Given a task with a short name and a detailed description
      When it is read with get_task
      Then its full description is returned
      And its declared dependencies and unfinished prerequisites are returned

    Scenario: A list provides summaries rather than full task bodies
      Given tasks with detailed descriptions and completion evidence
      When they are listed
      Then the list contains their names, status, and dependencies
      And the full descriptions and evidence remain readable through get_task

    Scenario: A task name can change without changing its identity
      Given a pending task with an assigned id
      When its subject and description are updated
      Then its id stays the same
      And its updated name and details are returned

    Scenario: Dependencies can be updated after tasks are created
      Given two independent pending tasks
      When one is updated to depend on the other
      Then it reports that prerequisite as unfinished
      And it cannot start until the prerequisite completes

    Scenario: Invalid dependency edits leave the task unchanged
      Given tasks with valid dependency relationships
      When an edit names an unknown task, the task itself, or a dependency cycle
      Then the edit is refused
      And no part of that edit is recorded

    Scenario: Content edits and status changes use separate calls
      Given a task with recorded content and status
      When one update supplies content edits and a status change
      Then the call is refused with a separate-call instruction
      And the task stays unchanged

    Scenario: New unfinished dependencies do not invalidate an active or completed task silently
      Given an in-progress or completed task
      When an edit adds an unfinished prerequisite
      Then the edit is refused and says to reopen or finish prerequisites first
      And the task retains its earlier dependency relationships

  Rule: A row is what a person reads

    Scenario: Lists show complete titles without expansion
      Given tasks with titles wider than the terminal and separate descriptions
      When the task list is rendered in its default state
      Then each stored title wraps in full without an ellipsis
      And descriptions do not replace the titles
      And every rendered line fits the terminal width


    Scenario: Task tools share one display label
      Given the four registered task tools
      When their results are rendered
      Then every row uses the tasks label and its create, get, list, or update action
      And progress reads as in progress rather than in_progress
      And the registered tool names and structured statuses remain unchanged

    Scenario: Expanded task fields have named sections
      Given a task has description, verify, and dependency fields
      When its result is expanded
      Then Description introduces the full description
      And Verify introduces the full verification prompt on separate lines
      And dependency relationships follow the description and verification sections
      And each section appears once without changing stored field values

    Scenario: Dependency relations are visible before expansion
      Given a task with declared dependencies and unfinished prerequisites
      When its result is collapsed
      Then it identifies its dependency ids and unfinished prerequisites
      And expansion preserves the full dependency relationships without duplicate rows

    Scenario: The row is bound when the extension is loaded
      Given the package's extension entry
      When it registers the tool
      Then the result is rendered as a lifecycle row
      And the row leads with what must be done rather than with the task id
      And its description and dependencies are available on expansion
      And holder and resource rows are absent from the transcript

    Scenario: A row without hidden content does not advertise expansion
      Given a task with no description, dependencies, or operation detail
      When its progress result is rendered
      Then the row contains only its name and status
      And it shows no expansion hint for holder metadata

    Scenario: The row never builds without real geometry
      Given a caller that supplies no renderer
      When the tool is registered
      Then Pi's own default paints the result
      And a row that cannot resolve terminal width is never constructed

  Rule: Only the current task file participates in the runtime

    Scenario: A retired filename is not loaded or modified
      Given only a retired task file exists for the session
      When the extension starts and a new task is created
      Then no task from that file enters the runtime
      And the current tasks.json contains only the new task
      And the retired file stays byte-identical

    Scenario: Current task data wins without a retired-file fallback
      Given tasks.json and a retired file both exist
      When the extension starts
      Then only tasks.json is loaded
      And neither source file is changed by the read

    Scenario: Retired persistence helpers are absent from the package interface
      Given the task package entry
      When its exports are inspected
      Then only current task path helpers are available
      And no retired-file resolver or path helper remains

  Rule: An installed-alone task set survives a restart

    Scenario: A standalone task set is written after every change
      Given @fradser/pi-tasks installed with nothing beside it
      When a task is created, taken, and completed
      Then the task file holds the result
      And a later session reading that file sees the same task

    Scenario: A task set with participants but no coordinator still writes its file
      Given a participant registry published beside the task set
      And no layer that claimed the task set's store
      When a task is created
      Then the task file holds it
      And the task set reports that it has participants, so nobody mistakes this for a single-participant task set

    Scenario: A task set that cannot be read is reported, not overwritten
      Given a durable task set this process cannot read
      When the session starts
      Then the task set is left untouched on disk
      And the tool reports why rather than presenting an empty task set
      And this process does not become the writer for a file it failed to read

    Scenario: A session the process cannot write to does not inherit the last one's writer
      Given a session whose task file this process wrote
      When the user switches to a session whose task file cannot be read
      And a task is created
      Then the earlier session's task file is left exactly as it was
      And the new session's task file is left untouched on disk
      And the tool reports why rather than presenting an empty task set

    Scenario: A coordinator beside the task set keeps sole ownership
      Given a layer that already owns this task set's store
      When the session starts
      Then this package does not attach a second writer
      And exactly one writer is ever active for the task file
      And the task set that layer loaded is left exactly as it loaded it

    Scenario: A restored in-progress task is not handed straight back out
      Given a task set holding a task that was in progress when it was written
      When a later session reads it
      Then no participant is recorded as holding it
      And it returns to `recovery_hold`

    Scenario: A durable task set that lost a field is read, not crashed on
      Given a durable task set whose task is missing an array it should carry
      When a later session reads it
      Then the task is restored with that array empty
      And the task set can be listed and taken from
