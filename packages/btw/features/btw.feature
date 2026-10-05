Feature: Read-only side questions

  Scenario: Input focus and editing follow the host
    Given the overlay contains a completed answer
    When the host changes overlay focus
    Then the composer follows the host focus
    And Home and End edit the question instead of scrolling the answer

  Scenario: Small terminals retain essential controls
    Given a terminal has at least 8 rows and 20 columns
    When the overlay renders in any turn state
    Then its rows fit within the 80% overlay height limit
    And the composer remains visible after an answer
    And smaller terminals display a close action and size requirement

  Scenario: Native wheel input and invalidation preserve the turn
    Given an answer viewport or an active turn
    When the host sends a normalized wheel event or invalidates caches
    Then wheel input scrolls only the answer
    And invalidation does not stop active animation

  The btw extension answers a side question in an isolated Pi child process
  without adding a session or leaving temporary prompt material behind.

  Background:
    Given the pi-btw-fradser extension is installed

  Scenario: Side-question feedback uses the shared TUI notification abstraction
    Given a side-question command needs to display validation feedback
    When it notifies the user
    Then it uses pi-kit's portable notification helper with the requested level

  Scenario: A child Pi run is configured read-only
    When a side question starts
    Then the child runs in print JSON mode without a session
    And its allowed tools are read, grep, find, and ls
    And bash, edit, and write are excluded

  Scenario: A long side prompt exists only for the child lifetime
    Given a side prompt exceeds the command-line argument limit
    When the child is running
    Then the prompt is passed as a private temporary @file
    And the temporary @file exists while the child needs it
    When the child terminates
    Then the temporary prompt file and its containing directory are removed

  Scenario: A long side prompt is cleaned up when the child cannot launch
    Given a side prompt exceeds the command-line argument limit
    When the child process emits a launch error
    Then the side question returns a failed result
    And the temporary prompt file and its containing directory are removed

  Scenario: Multi-turn side questions include conversation history in the prompt
    Given an initial side question has been answered
    When a follow-up side question is asked
    Then the prompt includes the side conversation history
    And the prompt includes the new side question
    And the child process executes without persisting a session

  Scenario: The btw overlay covers the main session input area
    Given the main session has its input TUI visible
    When the btw overlay opens
    Then the overlay is rendered directly over the main session input area
    And the overlay has no bottom margin
    And the answer viewport leaves room for the composer and footer within the 80% overlay height limit

  Scenario: Side-question overlay uses pi-kit's shared panel frame
    Given an interactive side question overlay
    When its conversation is rendered
    Then it uses pi-kit's shared panel renderer for the border, header, body, and footer

  Scenario: Multi-turn overlay maintains turns and aggregates token usage
    Given an interactive side question overlay
    When an initial question and a follow-up question are answered
    Then the overlay displays all conversation turns
    And the overlay does not display a redundant header title for the initial question
    And each conversation turn displays its question with You and its answer with btw
    And the footer aggregates token usage and cost across turns
    And the follow-up composer uses two full-width horizontal separators instead of a boxed frame
    And the follow-up composer keeps equal spacing on both sides of the input area
    And conversation separators span the available width with equal side spacing
    And the overlay does not report nonexistent hidden lines
    And conversation separators are longer than the content text and centered
    And the internal overlay separator marker is never displayed

  Scenario: Side answers render Markdown formatting
    Given an interactive side question overlay
    When the side child returns an answer containing headings, emphasis, lists, and code
    Then the overlay renders the answer through the Markdown component
    And block-level Markdown at the start of an answer is not joined to the btw label

  Scenario: Side answers are constrained to concise responses
    Given a side question prompt is built
    When the child receives its instructions
    Then it is told to answer in at most five short bullets
    And it is told to stay within a short word or character budget
    And it is told not to repeat the question or write a report

  Scenario: Side context stays compact
    Given a current session contains many messages
    When the side question context is built
    Then at most four recent messages are included
    And the context is capped at 4000 characters including the truncation marker
    And selected messages remain in chronological order

  Scenario: Context limits can disable the excerpt
    Given a context message or character limit is zero
    When the side question context is built
    Then the excerpt is empty

  Scenario: A cancelled follow-up cannot replace a later answer
    Given an initial side question has been answered
    And a follow-up question is still loading
    When the user cancels the follow-up and asks another question
    And the cancelled question returns a late answer
    Then the overlay keeps only completed turns and the new answer

  Scenario: Excessive side output is capped before display
    Given the side child returns an unusually long answer
    When the JSONL output is parsed
    Then the displayed answer is capped at 6000 characters

  Scenario: Side-question cancellation observes child close
    Given a side-question child is still running
    When the abort signal or timeout fires
    Then the child receives graceful termination before escalation
    And the prompt directory is removed only after the child closes

  Scenario: A pre-cancelled side question never starts a child
    Given a side-question abort signal is already cancelled
    When btw starts the child
    Then no child process is spawned
    And the result is a cancelled failure without assistant text

  Scenario: A stream failure keeps its diagnostic ahead of child stderr
    Given a side-question child writes stderr beyond the display cap before an oversized JSONL record
    When btw terminates the child for the stream limit
    Then the returned diagnostic starts with the stream-limit reason
    And the captured child stderr follows the reason

  Scenario: Side-question children do not discover extensions
    Given a side question starts a Pi child
    When btw builds the child command
    Then extension discovery is disabled
    And the read-only tool allowlist remains in force

  Scenario: Side-question CLI resolution rejects unrelated packages
    Given the current process entry belongs to an unrelated package whose name contains pi
    When the child CLI is resolved
    Then btw ignores that entry and uses an installed coding-agent CLI or PATH pi
