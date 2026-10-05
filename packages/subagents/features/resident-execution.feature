Feature: A subagent independently owns its execution lifecycle

  Rule: A launch applies the child's declared configuration

    Scenario: Shared execution uses the caller's directory and launch model
      Given a child launched from a directory different from the process directory
      When its start is accepted
      Then its working directory is the caller's directory
      And its effective model and thinking level are recorded and passed to execution

    Scenario: A disk-defined role receives ordinary scratch storage and private history
      Given a canonical disk agent.md with no persistence or workspace flags
      When it starts, settles, receives another input and later stops
      Then Memory and its private project session apply throughout
      And its cwd stays the original project with the scratch path explicit
      And neither settlement nor stop performs Git, preservation or release operations

  Rule: Explicit tools only narrow an existing role

    Scenario: An existing role cannot be widened by a call
      Given a disk-defined role granting read only
      When a caller requests bash
      Then the start is refused before spawning or reserving a name

    Scenario: An empty explicit grant removes file and shell tools
      Given a disk-defined role granting read and bash
      When the caller requests an empty grant
      Then the child has no file or shell tools
      And its scope-derived Memory capability remains available

  Rule: Sending input to a resident addresses exactly one idle incarnation

    Scenario: An idle resident receives its role on its first send
      Given a resident started without a prompt
      When the caller sends input to its exact session
      Then the role is delivered once with that input
      And accepted input starts work in that same session

    Scenario: Repeated sends return distinct settled results for either lifetime
      Given a temporary or durable resident that returned one answer and is idle
      When the caller sends to its exact session again
      Then another result returns without creating another process
      And the role and launch paths are not repeated

    Scenario: A previous result's delivery retry does not answer the next input
      Given an idle resident with its previous result awaiting one delivery retry
      When another input is accepted before that retry runs
      Then the previous result is still delivered once with its original turn
      And a death during the new unanswered input is still reported

    Scenario: A coalesced answer arrives before the input acknowledgement
      Given an idle resident receiving its second input
      When its answer settles synchronously before the positive acknowledgement
      Then both answers are delivered once in sequence
      And it remains IDLE and accepts a third input

    Scenario: Late progress cannot revive a confirmed-stopped incarnation
      Given a confirmed-stopped child
      When its old callbacks deliver streaming progress
      Then it remains stopped and accepts no send or interrupt

    Scenario: A hosted temporary child accepts further input in the same incarnation
      Given a host with acknowledged resident controls and a session-scoped child
      When its first answer settles and the caller sends another input to its exact handle
      Then the host acknowledges that input without another process or history reset
      When the caller interrupts its working exact handle
      Then the host acknowledges steering without opening another input sequence
      And the host remains the only result owner for both settled answers

    Scenario: Hosted input retains the host's uncertain authority
      Given an idle hosted resident with a native input control
      When its host reserves the sequence and cannot confirm acknowledgement
      Then the host receives the original idle state before its own reservation
      And the tool reports failure without restoring idle or discarding host authority

    Scenario: A host without resident controls cannot create an unusable resident
      Given a published host without acknowledged send and interrupt controls
      When a caller starts a temporary child
      Then the missing capability is explicitly refused before any process starts
      And controls never fall through to a standalone process

    Scenario: Busy or retired sessions receive no input
      Given a session that is working or has been replaced
      When the caller sends input to that exact handle
      Then input is refused without reaching a process

    Scenario: Rejected input does not claim a working turn
      Given an idle resident
      When the runtime rejects its input
      Then the refusal is reported and the resident remains idle

  Rule: An interrupt steers a turn in flight without ending it

    A working child is the one case `send` refuses, and it is the case a Leader
    most often needs: the child is on the wrong path and re-explaining after the
    turn is a turn wasted. Steering is not stopping — the turn continues, and its
    settled answer still returns exactly once.

    Scenario: A working resident receives a steer
      Given a resident that is working on a turn
      When the caller interrupts its exact session with input
      Then the input reaches that process without opening a new turn
      And the receipt waits for correlated native RPC acknowledgement
      And the resident is still working in the same session

    Scenario: An uncertain steering acknowledgement does not claim redirection
      Given a working resident whose steering acknowledgement times out
      When the caller interrupts its exact session
      Then the tool reports uncertain delivery without claiming acceptance
      And the resident keeps its working turn and result authority

    Scenario: An idle session cannot be interrupted
      Given an idle resident
      When the caller interrupts its exact session
      Then the interrupt is refused and the refusal names the action that fits

    Scenario: An interrupt does not suppress the turn's settled result
      Given a working resident that was interrupted
      When its turn settles
      Then exactly one Session Result returns for that turn

  Rule: Startup confirmation belongs to its original incarnation

    Scenario: A positive acknowledgement arrives after the child closed
      Given a start awaiting its native readiness or first-input acknowledgement
      When that child closes before acknowledgement succeeds
      Then startup is refused and the closed handle is not reported as living

    Scenario: An old startup acknowledgement cannot report a replacement
      Given a start awaiting confirmation and a same-name successor after confirmed close
      When the old positive acknowledgement arrives
      Then the old start is refused without modifying or controlling the successor

  Rule: Inspection reads known facts without requiring a living process

    Scenario: A known stopped incarnation remains inspectable
      Given an exact incarnation retained on the roster after a settled answer and confirmed stop
      When the caller inspects its complete exact handle
      Then inspection succeeds and reports stopped with the same handle and bounded answer
      And inspection changes no roster state and starts or controls no process

    Scenario: Unexpected closure remains inspectable for diagnosis
      Given a known child that closed unexpectedly and is retained as stopped
      When the caller inspects its exact handle
      Then inspection succeeds and carries the recorded closure error
      And it does not claim that the stopped child is alive or that its work succeeded

    Scenario: Long stopped diagnostics have a bounded read-only preview
      Given a known stopped entry with a recorded startup or runtime error longer than the diagnostic budget
      When the caller inspects its exact handle or lists retained sessions
      Then structured details and model-visible diagnostics contain a sanitized 1000-character preview
      And truncation is explicitly marked
      And the complete raw diagnostic and roster state remain unchanged

    Scenario: Reading a stopped incarnation does not grant control
      Given a known stopped incarnation
      When the caller sends, interrupts or stops its exact handle
      Then each control is refused without reviving or controlling a process

    Scenario: An unknown or replaced handle never reads a successor
      Given a same-name successor has replaced the original roster entry
      When the caller inspects the predecessor or an unknown complete exact handle
      Then inspection reports no known session for that handle
      And it never substitutes the successor

  Rule: Retired controls cannot retain a parent's temporary context

    Scenario: Confirmed shutdown retires only its exact control bindings
      Given a stopped incarnation and a same-name live successor
      When the parent retires controls for the stopped exact handle
      Then only the old resident and host bindings are removed
      And the successor remains controllable
      And an unconfirmed living handle cannot have its controls retired

  Rule: Stopping records intent before observing closure

    Scenario: Closure during termination is a planned ending
      Given a child working on a turn
      When its close callback runs before termination returns
      Then no unexpected-ended notice is delivered
      And the stop receipt retains the fact that work was interrupted

    Scenario: An unconfirmed stop retains the exact handle and stop intent
      Given a child whose close cannot be confirmed
      When the caller stops it
      Then its name and stop intent are retained
      And send and interrupt are refused until the outcome is known
      And another stop can retry confirmation
