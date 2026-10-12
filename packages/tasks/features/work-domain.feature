Feature: Task domain rules and durable task set persistence

  @fradser/pi-tasks owns what a Task is, how Tasks depend on and exclude each
  other, and how the task set survives a restart. It owns no process, roster, or
  message concept: `resourcesConflict` is the primitive, and deciding which held
  assignments to compare against it belongs to whoever owns the roster.

  Rule: A derived Task id stays readable and filesystem-safe

    Scenario: A subject becomes a slug
      Given the subject "Polish login flow"
      When a Task id is derived
      Then the id is "polish-login-flow"

    Scenario: Punctuation and case do not survive
      Given a subject containing capitals, underscores, and repeated separators
      When a Task id is derived
      Then the id contains only lowercase letters, digits, and single dashes
      And it neither starts nor ends with a dash

    Scenario: A collision gets a numeric suffix instead of overwriting
      Given "polish-login-flow" is already taken
      When a Task id is derived from the same subject
      Then the id is "polish-login-flow-1"
      And deriving again with both taken yields "polish-login-flow-2"

    Scenario: A long subject is truncated at a word boundary
      Given a subject longer than the id limit
      When a Task id is derived
      Then the id is at most the limit long
      And the id does not end inside a word
      And it does not end with a dash

    Scenario: A subject with no usable characters still yields an id
      Given a subject of only punctuation
      When a Task id is derived
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
      Given a superseded Task whose replacement is absent
      When the canonical dependency is resolved
      Then the result is undefined
      And a self-referential or cyclic chain is likewise refused

    Scenario: A dependency cycle is detected before creation
      Given a graph where "a" depends on "b" and "b" depends on "a"
      When the graph is checked
      Then a cycle is reported
      And an acyclic graph with a shared dependency reports none

  Rule: The task file is durable and refuses to guess

    Scenario: A written task set reads back exactly
      Given a task set holding two Tasks
      When it is written and read again
      Then both Tasks are returned unchanged

    Scenario: An absent task set is a fresh session
      Given a task set path that does not exist
      When the task set is read
      Then the result is undefined rather than an error

    Scenario: A present but unreadable task set is never an empty task set
      Given a task file whose contents are not valid JSON
      When the task set is read
      Then the call raises rather than returning empty
      And the message names the file
      And the caller can archive the preserved file instead of losing durable Tasks

    Scenario: An incompatible version is rejected, not migrated
      Given a task file carrying an older runtime version
      When the task set is read
      Then the call raises naming the found and expected versions

    Scenario: Task set state is scoped per session
      Given two different session files in the same working directory
      When their task set directories are resolved
      Then the directories differ
      And resolving the same session file twice gives the same directory
      And with no session file the working directory is the scope

  Rule: A contested intent has exactly one winner

    Scenario: The first publisher wins and the second is told
      Given two intents for the same Task id
      When each is published
      Then exactly one reports success
      And one marker file exists

    Scenario: A marker name cannot escape its directory
      Given a Task id containing path traversal
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

  Rule: A completion's holder check applies only to work that is held

    Scenario: A restored pending task with a stale holder completes through the fallback
      Given a restored pending task that still names a holder who is gone
      When another caller completes it with the checks on
      Then the completion is accepted
      And no refusal calls that task in progress
      And a task that was never taken is still refused with the checks on

  Rule: A failed attempt leaves no gate answer behind

    Scenario: A failure clears the verdict the earlier attempt recorded
      Given a gated task completed with a passing verdict
      And a reopened and retaken second attempt
      When that attempt completes with outcome failed
      Then the recorded verdict and gate are gone
      And the blocker stays as evidence for the next attempt

  Rule: A refusal names why, in one shape

    Scenario: Every refusal carries a machine code and a reason
      Given a refused creation, edit, take, completion, reopen, bind, or marker
      When the caller inspects the refusal
      Then it carries a machine code from one closed set
      And it carries a human reason
      And it names the task, holder, or prerequisite it is about when it is about one

    Scenario: One refusal shape across every operation
      Given the same caller reads five different refusals
      When it inspects each result
      Then every one carries a refusal, an optional detail, and a reason
      And no result carries a second field holding the same sentence

    Scenario: A caller branches on the code rather than on the sentence
      Given a take refused because another holder has the task
      When the caller needs to know which rule refused it
      Then it reads the code alone
      And the prose is free to name the rule in whatever words read best

  Rule: The package has no coordination coupling

    Scenario: Nothing in @fradser/pi-tasks imports a roster, process, or mailbox concept
      Given the package source
      When its imports are inspected
      Then only node builtins, the Pi core peer, and pi-kit appear
      And no module references teammates, spawning, or peer mail
      And no module names a sibling package, so nothing here can be imported later without failing

    Scenario: The environment binding a participant is claimed through belongs to the task set
      Given a spawner that gives a child a holder name
      When the child asks who it is on the task set
      Then it reads the variable this package exports, not one the spawner named for itself
      And renaming the spawner's own variables changes nothing here

    Scenario: A published participant registry is read without importing its owner
      Given a process layer that published a holder registry beside this package
      When the task set checks who holds what
      Then it reads that registry through the published shape
      And it applies its own conflict primitive to the holders the registry reports
      And a holder's assignment reaches the registry rather than a private copy
      And with no registry published the task set stays single-session

    Scenario: The published shape is declared once and both sides import it
      Given the contract that crosses between the task set and a process layer
      When each side is inspected
      Then the shape and the registry key are declared in the shared runtime alone
      And neither side keeps a second copy that could drift
      And a field renamed on one side alone fails to typecheck rather than misbehaving

    Scenario: A stopped or replaced participant is refused through a question, not a comparison
      Given a participant that stopped and one that was replaced by a new incarnation
      When the task set checks whether either can act
      Then it asks the publishing layer, which is the only one that knows
      And this package never reads a participant's liveness or incarnation itself
