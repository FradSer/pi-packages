# The final three-tool surface: one tool per package, one meaning per action,
# and no ownership field on a task.
#
# This file is the contract the split is executed against. Every scenario here is
# currently RED against `work` / `agent_event` and goes GREEN when the tool
# surface lands. Assertions are updated to the new names, never weakened, and the
# scenarios at the end pin the cutover so a removed name cannot come back.

Feature: Agent Teams tool surface

  Background:
    Given the installed package set is one of: subagents, tasks, or the agent-teams bundle

  # ── One tool per package ────────────────────────────────────────────────

  Scenario: each package registers exactly the tool it implements
    When the extension loader reports the registered tools
    Then "@fradser/pi-subagents" registers "agent" and nothing else
    And "@fradser/pi-tasks" registers "task" and nothing else
    And "@fradser/pi-agent-teams" registers "message" and nothing else
    And no package registers a tool it does not implement

  Scenario: a package installed alone is usable
    Given only "@fradser/pi-tasks" is installed
    When the model lists tasks and takes one
    Then the main session holds the task and no process is required
    And "@fradser/pi-subagents" is absent
    And "@fradser/pi-agent-teams" is absent

  # ── agent: one spawn verb ───────────────────────────────────────────────

  Scenario: a prompted child works immediately and persists afterwards
    Given an Agent "scout" is running
    When the model calls agent start with name "scout" and a prompt
    Then a Work Session runs that prompt to a terminal result
    And the result is reported to the leader automatically
    And the Work Session stays alive and idle afterwards
    And no task is created

  Scenario: an unprompted child joins the pool and takes work itself
    Given an Agent "scout" is running
    When the model calls agent start with name "scout" and no prompt
    Then no model turn runs
    And the Agent is woken by board notice
    And the Agent takes a task by updating that task's status itself
    And the leader cannot name the Agent on the task

  Scenario: inspect and stop address one incarnation only
    Given an Agent "scout" was stopped and a replacement "scout" started
    When the model calls agent inspect with the retired session handle
    Then the call is refused
    And the error names the replacement handle
    And calling inspect with the replacement handle succeeds

  Scenario: fork without a prompt is legal
    Given the leader has active conversation context
    When the model calls agent start with fork and no prompt
    Then a context-primed idle Work Session is created
    And the call is not refused

  # ── task: no ownership field, derived lease ─────────────────────────────

  Scenario: taking a task is the act of moving it into progress
    Given a pending task "t1" with no holder
    When the model calls task update with id "t1" and status "in_progress"
    Then "t1" is held by the calling participant
    And the task records no declared owner

  Scenario: two participants racing for one task produce exactly one holder
    Given a pending task "t1" with no holder
    When two participants call task update with status "in_progress" at the same time
    Then exactly one succeeds
    And the other is refused and told who holds "t1"
    And the loser does not receive a second copy of the task

  Scenario: a task cannot be taken by a name the model supplies
    When the model calls task update on any task
    Then no parameter accepts a participant name
    And no participant other than the caller can be recorded as holder

  Scenario: the task schema is identical in every process
    When the task tool is registered in a leader process and in a worker process
    Then both registrations expose the same actions
    And neither exposes a leader-only or worker-only action

  Scenario: submitting a failure is explicit and never prose
    Given a task "t1" is in progress and held by a worker
    When the worker cannot proceed and reports the blocker as an ordinary final answer
    Then the task is still in progress
    And the failure is not recorded
    When instead the worker calls task complete with outcome "failed"
    Then the task returns to pending
    And the recovery hold is set
    And the blocker is retained as evidence

  Scenario: the recovery hold requires a stated reason
    Given a task "t1" is pending with the recovery hold set
    When a participant takes it without a reason
    Then the call is refused
    When the participant takes it with a reason
    Then the task is held and the hold is cleared
    And the reason is retained

  Scenario: reopening a completed task is refused while a dependent runs
    Given a completed task "t1" and a task "t2" that is in progress and depends on "t1"
    When the model moves "t1" back to pending
    Then the call is refused
    And the error names the participant holding "t2"

  Scenario: no verb releases work explicitly
    When the board tool surface is enumerated
    Then no action is named release, abandon, reclaim, assign, claim, submit, supersede, or get

  # ── message: point to point, no threading ──────────────────────────────

  Scenario: two agents message each other directly
    Given a leader and two Agents "alpha" and "beta" are running
    When "alpha" sends a message to "beta"
    Then "beta" receives it with "alpha" recorded as the sender
    And no leader is required in the path

  Scenario: a request wakes the recipient and an inform does not
    Given Agent "beta" is idle
    When "alpha" sends a request to "beta"
    Then "beta" is woken
    When "alpha" sends an inform to "beta"
    Then "beta" is not woken

  Scenario: the sender is never caller supplied
    When a message is sent
    Then the sender is taken from the runtime
    And no parameter accepts a sender identity

  Scenario: a message carries no thread and no attachment
    When the message tool surface is enumerated
    Then it declares no action parameter
    And it accepts no reply reference
    And it accepts no recipient group, broadcast, or attachment

  # ── Bundle ──────────────────────────────────────────────────────────────

  Scenario: the bundle installs all three tools
    Given only "@fradser/pi-agent-teams" is installed
    When the extension loader reports the registered tools
    Then "agent", "task", and "message" are all present
    And each is registered exactly once

  Scenario: a dependency is loaded through its extension entry, not its barrel
    When the bundle manifest is read
    Then each dependency is listed as a path under node_modules
    And each listed path is an extension entry exporting a default function
    And no listed path is a library barrel

  # ── Cutover, pinned ─────────────────────────────────────────────────────

  Scenario: every removed tool name is refused
    When the model calls "work", "agent_event", "claim", "assign", "release",
      "abandon", "reclaim", "submit", "supersede", or "get"
    Then each call is refused as an unknown tool or unknown action
    And the refusal names the replacement where one exists

  Scenario: the removed status value is refused
    Given a task in progress
    When the model moves it with status "claimed"
    Then the call is refused
    And the error names "in_progress"
