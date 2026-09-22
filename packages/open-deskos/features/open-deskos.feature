Feature: Report this machine's Pi sessions to Open DeskOS, and drive a hosted Pi

  Scenario: Local installation works from any checkout location
    Given the repository is checked out outside the user's home in a path containing spaces
    When the user follows either language's local installation command from the checkout root
    Then Pi receives the absolute path to the Open DeskOS package
    And the command does not depend on a personal home-directory layout

  Scenario: A configured reporter opens a link and reports its session
    Given the machine has a Desk Link address and token
    When its Pi session starts
    Then it opens one Desk Link to Open DeskOS
    And it reports the session identity and its actual idle or running state

  Scenario: An unconfigured machine stays silent
    Given the machine has no Desk Link address or token
    When its Pi session runs
    Then no connection is attempted
    And no session is reported
    And no control connection is attempted

  Scenario: A resumed, reloaded, or forked session replays its durable JSONL tail
    Given a resumed, reloaded, or forked Pi session has complete user and assistant messages in its current session file
    And its file may end with an unfinished record
    When that session starts its Desk Link reporter
    Then the reporter sends only the bounded complete JSONL message tail for that current session
    And later live messages are sent after the replay without replacing it

  Scenario: A stale replay cannot cross a session switch
    Given a reporter starts reading an older session tail
    When the current Pi session changes and then returns to the same session identity
    Then only the tail belonging to the latest start is sent
    And a new or reasonless session start replays no durable tail

  Scenario: Reported events obey the local bounds
    Given a session produced more activity than the event bound
    When the reporter sends its events
    Then at most the bounded number of events are retained or sent
    And every event kind preserves multiline content within its own byte bound
    And tool results preserve complete multiline Markdown within the result byte bound

  Scenario: A long outage bounds what the reporter retains
    Given the Desk Link is offline
    When the session keeps producing events beyond the event bound
    Then the oldest events are dropped
    And the reporter's retained events stay bounded
    And no more than one unsent snapshot is held

  Scenario: A dropped link reconnects with a growing wait
    Given a Desk Link was established and then dropped
    When the reporter reconnects
    Then each attempt waits a longer interval than the one before
    And the interval never exceeds the configured maximum
    And only one link is open at a time

  Scenario: A reconnected link reports the current session state
    Given the Desk Link dropped while a session was running
    When the link reconnects
    Then the reporter sends the current session state
    And it replays the complete bounded retained event tail even if it was already sent
    And it does not replay an unbounded backlog

  Scenario: The reporter never acts inside a reported session
    Given a Desk Link is connected
    When the reporter observes messages and tool results
    Then it only reads them
    And it never sends a prompt into a reported session, blocks a turn, or mutates a message

  Scenario: A machine without a control credential cannot control
    Given the machine has a Desk Link address and token but no control credential
    When its Pi session runs
    Then it reports exactly as a report-only machine does
    And the console does not offer to list, launch, attach to, prompt, cancel, or end a Hosted Pi

  Scenario: A Console opens its own connection
    Given the machine has a control credential
    When it lists, launches, or reads history
    Then that work uses its own control connection to the same listener
    And the reporting connection's records, backoff, and session ownership are unchanged

  Scenario: The control credential is never transmitted
    Given the machine opens a control connection
    When the desk challenges it with a one-time nonce and hmac-sha256
    Then the machine answers with a proof over the fixed domain, version, nonce, machine, and Console session identity
    And the reporting token appears only in control-hello
    And the independent control credential never appears in any record the machine writes
    And an unsupported version is reported explicitly before a credential failure

  Scenario: Requests correlate retries and attachments independently
    Given the Console lists, launches, reads history, and mutates a Hosted Pi
    When it writes version 2 control records
    Then every request carries a request ID
    And launch, prompt, cancel, and end carry a mutation ID
    And held attach traffic carries an attachment ID
    And cancel may carry a turn ID or precondition so a delayed duplicate cannot cancel a later turn

  Scenario: A Console holds a connection only while attached
    Given the machine is attached to a Hosted Pi
    When it is attached
    Then one control connection is held
    And it is closed once the machine is no longer attached
    And losing it ends neither the Hosted Pi nor the reporting link

  Scenario: Fresh attach starts at the current boundary
    Given the machine has never attached to a Hosted Pi
    When it attaches without a saved position
    Then it sends after null and begins at the desk's current boundary
    And it does not fetch old history implicitly
    And old content remains available through an explicit history request

  Scenario: Resumed attach catches up atomically from the last applied position
    Given the machine previously applied events up to a physical position in a Hosted Pi's session log
    When it attaches again
    Then it sends that position and consumes ordered catch-up through the caught-up boundary on the held connection
    And it applies no position twice
    And increasing positions need not be consecutive when non-message log entries intervene
    And a regressing position is diagnosed
    And it keeps no replay window

  Scenario: Only a bounded tail enters the driving session's context
    Given an attached Hosted Pi producing more events than the injection bound
    When those events arrive
    Then the driving session receives a bounded tail rather than every event
    And the complete content stays available on demand rather than in context

  Scenario: Tools cover the console without a status or detach tool
    Given a Console is configured
    When the assistant inspects its tools
    Then list, start, attach, prompt, cancel, end, and history are available
    And no separate status tool and no detach tool are registered

  Scenario: Link diagnostics never occupy the footer
    Given the machine is configured or unconfigured
    When sessions start, report messages, switch, or shut down
    And a configured link connects, drops, or reconnects while idle
    Then Open DeskOS never sets or clears a footer status
    And it never installs a custom footer or working-directory suffix
    And diagnostics are available only through the open-deskos command's menu and its status argument

  Scenario: The command opens the same menu in every configuration
    Given a machine that is unconfigured, a machine that is report-only, and a machine that is a configured Console
    When the user runs the open-deskos command with no arguments in each case
    Then the same menu opens with the same rows
    And a row that is unavailable names the reason rather than disappearing

  Scenario: Missing configuration is diagnosed on demand
    Given the machine has no Desk Link address or token
    When the user opens the open-deskos command's menu
    Then the missing configuration variables are shown
    And the console row states that it needs a control credential rather than disappearing

  Scenario: The link state is visible from inside Pi
    Given a Desk Link is connected or offline
    When the user opens the open-deskos command's menu or passes its status argument
    Then the reported link state, machine, session count, and event count are shown

  Scenario: The console surface owns its own input
    Given a Console surface is open in a Pi session
    When the user types at the terminal
    Then the surface consumes input through Pi's own custom UI seam
    And global terminal input is never intercepted
    And no footer status is added
