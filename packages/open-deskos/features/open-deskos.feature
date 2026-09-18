Feature: Report this machine's Pi sessions to Open DeskOS

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

  Scenario: Reported events obey the local bounds
    Given a session produced more activity than the event bound
    When the reporter sends its events
    Then at most the bounded number of events is retained or sent
    And non-result events remain single-line summaries of at most 200 characters
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
    Then each attempt waits a longer interval than the one before it
    And the interval never exceeds the configured maximum
    And only one link is open at a time

  Scenario: A reconnected link reports the current session state
    Given the Desk Link dropped while a session was running
    When the link reconnects
    Then the reporter sends the current session state
    And it replays the complete bounded retained event tail even if it was already sent
    And it does not replay an unbounded backlog

  Scenario: The reporter never acts inside the session
    Given a Desk Link is connected
    When the reporter observes messages and tool results
    Then it only reads them
    And it never sends a prompt, blocks a turn, or mutates a message

  Scenario: Link diagnostics never occupy the footer
    Given the machine is configured or unconfigured
    When sessions start, report messages, switch, or shut down
    And a configured link connects, drops, or reconnects while idle
    Then Open DeskOS never sets or clears a footer status
    And it never installs a custom footer or working-directory suffix
    And diagnostics are available only through the open-deskos command

  Scenario: Missing configuration is diagnosed on demand
    Given the machine has no Desk Link address or token
    When the user runs the open-deskos command
    Then the missing configuration variables are shown

  Scenario: The link state is visible from inside Pi
    Given a Desk Link is connected or offline
    When the user runs the open-deskos command
    Then the reported link state, machine, session count, and event count are shown
