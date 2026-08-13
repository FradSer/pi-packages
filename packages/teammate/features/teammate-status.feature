Feature: Teammate footer status visibility
  The footer status ("N teammate(s) | N unread message(s) | N active task(s), N total")
  must only appear once the team is real — an all-zero line ("0 teammate(s) | ...")
  must never be shown on session entry.

  Background:
    Given the @fradser/teammate extension is loaded

  Scenario: Fresh session with no teammates shows no footer status
    When a session starts with no registered teammates
    Then the footer status is cleared (nothing shown)

  Scenario: Registering the first teammate shows the summary
    Given no teammates are registered
    When a teammate is registered
    Then the footer status shows the real counts (e.g. "1 teammate(s) | 0 unread message(s) | 0 active task(s), 0 total")

  Scenario: Restored session with teammates shows the persisted summary
    Given a snapshot with 2 teammates and 1 unread message was persisted
    When a session starts
    Then the footer status reflects the restored counts

  Scenario: Status refresh stays visible after teammate operations
    When a teammate operation runs (send/assign/update/broadcast/spawn)
    Then the footer status updates to the new counts

Feature: Autonomous teammate workers
  Spawned workers are fully autonomous agents: they watch their own mailbox via
  the shared state file, process new messages on their own, and decide when to
  close. The parent never sleep-polls — it awaits the worker's own exit.

  Background:
    Given a teammate is registered and a task is assigned

  Scenario: Default spawn blocks until the worker closes itself
    When teammate_spawn runs with background=false (default)
    Then the tool call waits for the worker's autonomous exit
    And returns the worker's final report and the task outcome

  Scenario: Worker watches its mailbox while running
    Given the shared state file is published before spawn
    When a message arrives for the worker during its run
    Then the worker reads it, processes it, and replies via the state file
    And the parent merges the reply back into the board after exit

  Scenario: Worker decides when to close
    When the worker judges no more work is coming (idle window / explicit stop)
    Then it exits on its own
    And the task is marked completed/failed accordingly

  Scenario: Background spawn lets the worker outlive the tool call
    When teammate_spawn runs with background=true
    Then the tool returns immediately with the pid
    And the worker keeps watching its mailbox until it decides to close

Feature: Assignment notification consumption
  Assignment notifications ("New task: ...") are consumed when the task
  actually starts, so the footer unread count reflects things that need
  attention — not stale assignment history.

  Background:
    Given a task was assigned with a mailbox notification

  Scenario: Spawning a task consumes its notification
    When teammate_spawn runs the task
    Then the assignment notification for that task is marked read
    And the footer unread count drops

  Scenario: Marking a task in_progress consumes its notification
    When teammate_update_task sets the task to in_progress
    Then the assignment notification for that task is marked read

Feature: Teammate management (board lifecycle)
  The board is manageable end to end: teammates can be removed, finished tasks
  pruned, the whole board reset, and expired shared state dirs cleaned up.

  Background:
    Given a teammate team with tasks exists

  Scenario: Remove a teammate
    When teammate_remove runs for an idle teammate
    Then the teammate and its mailbox are deleted
    And the footer teammate count drops

  Scenario: Remove refuses a running teammate unless forced
    When teammate_remove runs for a teammate running a worker
    Then it fails with a clear error (unless force=true)

  Scenario: Prune finished tasks
    When teammate_cleanup runs without taskId
    Then all completed/failed/cancelled tasks are removed
    And the footer task count drops

  Scenario: Reset the board
    When teammate_reset runs
    Then all teammates, mailboxes, and tasks are wiped
    And the footer shows the empty state

  Scenario: Session lifecycle cleans state dirs
    Given shared state dirs were written by spawns
    When a session starts
    Then dirs older than the retention window are swept
    And when a session shuts down, its own state dir is removed

  Scenario: Team UI = passive widget + /teammate console (no key interception)
    Given a team exists
    Then a passive widget shows teammate rows and the leader-inbox alert
    And no global input listener is registered (model switching / history unaffected)
    When the user types /teammate
    Then a full-screen console opens and owns input
    And ↑/↓ select between the inbox row and teammates
    When Enter is pressed on a teammate row
    Then its full page opens with special sections (unread messages, tasks, mailbox)
    When r is pressed in a page
    Then an inline reply input appears (Enter sends, Esc cancels)
    When Enter is pressed on the inbox row
    Then the leader inbox page opens with messages from teammates
    When x is pressed on a running teammate
    Then its worker is stopped hard (SIGKILL)
    When Esc is pressed in the list
    Then the console closes

  Scenario: Selecting an agent shows its full running content
    Given a teammate has a task whose worker produced a final report
    When the user opens that teammate in the /teammate console
    Then the page shows the task description, the worker output, stderr, and usage
    And the task section renders the full content, not a one-line status

  Scenario: Remove a teammate
    When teammate_remove runs for an idle teammate
    Then the teammate and its mailbox are deleted
    And the footer teammate count drops

  Scenario: Remove refuses a running teammate unless forced
    When teammate_remove runs for a teammate running a worker
    Then it fails with a clear error (unless force=true)

  Scenario: Prune finished tasks
    When teammate_cleanup runs without taskId
    Then all completed/failed/cancelled tasks are removed
    And the footer task count drops

  Scenario: Reset the board
    When teammate_reset runs
    Then all teammates, mailboxes, and tasks are wiped
    And the footer shows the empty state

  Scenario: Session lifecycle cleans state dirs
    Given shared state dirs were written by spawns
    When a session starts
    Then dirs older than the retention window are swept
    And when a session shuts down, its own state dir is removed

  Scenario: Persistent team panel drives management (no menu, no footer status)
    Given a team exists and the prompt editor is empty
    When the user presses Shift+Down
    Then the panel selection moves to the next row (plain ↓/↑ stay history navigation)
    When the user presses Enter on a teammate row
    Then a FULL-SCREEN page opens for that agent (no popup) with special sections:
    - unread messages
    - assigned tasks
    - mailbox transcript
    And pressing r quick-replies, Esc/q closes the page
    When a teammate writes a message to the leader (mailboxes["agent"])
    Then the panel shows a selectable "N message(s) to you" row
    And Enter on it opens the full-screen leader inbox page
    And teammate_read_mailbox name=agent reads it without a registered teammate
    When the user presses Esc on a running teammate
    Then its worker is interrupted (SIGTERM)
    When the user presses x on a running teammate
    Then its worker is stopped hard (SIGKILL)
    When the whole team is idle for 30s
    Then the panel collapses to a summary row
    And no aggregate unread/task summary is shown in the panel
    And no teammate footer status is set
