Feature: A session learns the task tools exist

  The task tools register four names and their descriptions are sent to the
  provider in every request. A session that never learns when recording a task is
  warranted calls the tool by accident or not at all: measured over 1152 recorded
  sessions, `create_task` ran 17 times in 7 sessions while `bash` ran 78178 times.

  The trigger conditions therefore live in the surface that is already sent. A
  separate note injected into every request costs its text on every turn, and the
  session that needs it least — a one-line question — pays it too. Nothing in this
  package adds a message to a request.

  Rule: The trigger conditions live in the tool surface

    Scenario: create_task states when recording a task is warranted
      Given the registered create_task tool
      When a model reads its description
      Then it states that a task is for work with several steps or several files
      And it states that a task is for work that outlives the current turn
      And it states that a single edit is not a task

    Scenario: The surface states how a task differs from a goal
      Given the registered create_task tool
      When a model reads its description
      Then it states that a task is not a goal
      And it states that a goal keeps running until it is met
      And it states that a task is one unit of work

    Scenario: All four tools reach the model
      Given the package extension entry
      When its registered tools are read
      Then create_task, get_task, list_tasks and update_task are registered
      And each one carries a snippet saying what it is for

  Rule: One bounded note says when the situation calls for a task

    Scenario: A session with no open task receives the note
      Given a task set with no unfinished task
      When the model builds its context
      Then the context carries a capability note naming the four task tools
      And the note states when a task should be recorded
      And the note states how a task differs from a pi-goal goal

    Scenario: The note is bounded and never grows with the task set
      Given a task set holding many tasks
      When the model builds its context
      Then the note is identical to the note an empty task set produces
      And the note names no task, because the note is about the surface

    Scenario: The note is harness context and not a user message
      Given the note inserted into a request
      When the request is assembled
      Then the note is a system message after the prompt
      And no user message carries the note
      And the prompt keeps the first position

    Scenario: The note lands at a fixed position so each request prefixes the last
      Given two requests whose transcripts differ only by a later turn
      When both are built
      Then the note occupies the same index in each
      And the earlier request is a prefix of the later one

    Scenario: The note has one home in the sources
      Given the package sources
      When they are searched for the note marker
      Then exactly one source file carries it

  Rule: The repository instructions name when to use the task tools

    Scenario: The agent instructions state the trigger conditions
      Given the repository agent instructions
      When an agent reads them
      Then they name create_task, get_task, list_tasks and update_task
      And they state that a task is for work with several steps or several files
      And they state that a single edit is not a task
      And they record that the task tools do not reach a child process

  Rule: The settle reminder is bounded and reports unfinished work only

    Scenario: The reminder reports unfinished work and nothing else
      Given a task set holding an unfinished task
      When the model is about to settle
      Then the reminder reports the unfinished work once
      And it carries no capability text, because the surface carries that