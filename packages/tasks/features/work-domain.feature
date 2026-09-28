Feature: Work Item domain rules and durable board persistence

  @fradser/pi-tasks owns what a Work Item is, how Work Items depend on and exclude each
  other, and how the board survives a restart. It owns no process, roster, or
  message concept: `resourcesConflict` is the primitive, and deciding which held
  assignments to compare against it belongs to whoever owns the roster.

  Rule: A derived Work id stays readable and filesystem-safe

    Scenario: A subject becomes a slug
      Given the subject "Polish login flow"
      When a Work id is derived
      Then the id is "polish-login-flow"

    Scenario: Punctuation and case do not survive
      Given a subject containing capitals, underscores, and repeated separators
      When a Work id is derived
      Then the id contains only lowercase letters, digits, and single dashes
      And it neither starts nor ends with a dash

    Scenario: A collision gets a numeric suffix instead of overwriting
      Given "polish-login-flow" is already taken
      When a Work id is derived from the same subject
      Then the id is "polish-login-flow-2"
      And deriving again with both taken yields "polish-login-flow-3"

    Scenario: A long subject is truncated without leaving a trailing dash
      Given a subject longer than the id limit
      When a Work id is derived
      Then the id is at most the limit long
      And it does not end with a dash

    Scenario: A subject with no usable characters still yields an id
      Given a subject of only punctuation
      When a Work id is derived
      Then the id is the fallback rather than empty

  Rule: Resource tags describe a lease, not a string

    Scenario: Normalizing trims, drops empties, de-duplicates, and orders
      Given resources with padding, empty entries, leading and trailing slashes, and a duplicate
      When the set is normalized
      Then empties and duplicates are gone
      And the result is sorted
      And two callers describing the same lease cannot disagree through ordering

    Scenario: A resource conflicts with itself and its descendants
      Given the resource "firmware/sub-node"
      When it is compared against "firmware/sub-node" and "firmware/sub-node/app"
      Then both conflict

    Scenario: Unrelated siblings stay concurrently claimable
      Given the resource "firmware/sub-node"
      When it is compared against "firmware/other" and "firmware/sub-nodex"
      Then neither conflicts

    Scenario: An empty lease conflicts with nothing
      Given one side holds no resources
      When the two sides are compared
      Then there is no conflict

  Rule: Supersession chains resolve or are refused

    Scenario: A dependency follows a superseded chain to its replacement
      Given "a" was superseded by "b" and "b" by "c"
      When the canonical dependency of "a" is resolved
      Then it is "c"

    Scenario: A broken chain is refused rather than silently unclaimable
      Given a superseded Work whose replacement is absent
      When the canonical dependency is resolved
      Then the result is undefined
      And a self-referential or cyclic chain is likewise refused

    Scenario: A dependency cycle is detected before creation
      Given a graph where "a" depends on "b" and "b" depends on "a"
      When the graph is checked
      Then a cycle is reported
      And an acyclic graph with a shared dependency reports none

  Rule: The board file is durable and refuses to guess

    Scenario: A written board reads back exactly
      Given a board holding two Work Items
      When it is written and read again
      Then both Work Items are returned unchanged

    Scenario: An absent board is a fresh session
      Given a board path that does not exist
      When the board is read
      Then the result is undefined rather than an error

    Scenario: A present but unreadable board is never an empty board
      Given a board file whose contents are not valid JSON
      When the board is read
      Then the call raises rather than returning empty
      And the message names the file
      And the caller can archive the preserved file instead of losing durable Work

    Scenario: An incompatible version is rejected, not migrated
      Given a board file carrying an older runtime version
      When the board is read
      Then the call raises naming the found and expected versions

    Scenario: Board state is scoped per session
      Given two different session files in the same working directory
      When their board directories are resolved
      Then the directories differ
      And resolving the same session file twice gives the same directory
      And with no session file the working directory is the scope

  Rule: A contested intent has exactly one winner

    Scenario: The first publisher wins and the second is told
      Given two intents for the same Work id
      When each is published
      Then exactly one reports success
      And one marker file exists

    Scenario: A marker name cannot escape its directory
      Given a Work id containing path traversal
      When the intent is published
      Then the marker stays inside the intent directory

    Scenario: An intent missing holder identity is consumed with a reason
      Given a marker whose worker or spawnId is empty
      When an intent is taken
      Then no intent is returned
      And the diagnostic names the file and the reason
      And the marker is removed so it cannot block the queue

    Scenario: An invalid submission status is refused
      Given a marker whose status is neither completed nor failed
      When an intent is taken
      Then the diagnostic reports an invalid submission status

    Scenario: A half-written marker inside the grace is retried
      Given an unparseable marker younger than the publish grace
      When an intent is taken
      Then nothing is returned and nothing is removed
      And destroying an in-flight intent would otherwise strand its author

  Rule: The package has no coordination coupling

    Scenario: Nothing in @fradser/pi-tasks imports a roster, process, or mailbox concept
      Given the package source
      When its imports are inspected
      Then only node builtins, the Pi core peer, and pi-kit appear
      And no module references teammates, spawning, or peer mail
