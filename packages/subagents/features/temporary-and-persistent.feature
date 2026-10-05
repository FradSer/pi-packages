Feature: Disk definitions declare durable identity and inline roles remain temporary

  Rule: Every child stays resident after a settled result

    Scenario Outline: A result leaves the same incarnation idle and ready for input
      Given a <kind> child processing its first input
      When its complete answer settles
      Then that answer returns once and the child is IDLE
      And no termination, preserve, release or Git operation runs
      When the caller delivers a second input to the same exact handle
      Then its second answer returns once from that same incarnation
      And only stop or parent shutdown closes the child

      Examples:
        | kind      |
        | temporary |
        | durable   |

    Scenario: An authoritative empty answer remains a settled result
      Given a child whose completed assistant message is empty
      When its turn settles
      Then the exact empty result returns once and the child is IDLE
      And an earlier empty settle with no completed message consumes no delivery

  Rule: Only a valid disk agent.md declares durable identity

    Scenario: A prompt-only temporary child creates no private data
      Given no disk definition
      When a caller supplies a prompt and a minimal tool grant
      Then a uniquely named session-scoped child starts with no-session
      And no definition, Memory, workspace or private history is created

    Scenario: Every disk scope receives private data and Memory
      Given a valid user, project or project-local agent.md
      When a caller starts that name without any persistence flags
      Then the resolved scope and definition source are recorded
      And the child receives Memory and its own project-scoped private history
      And its launch cwd remains the original project
      And its ordinary scratch workspace and original project are explicit in prompt and environment
      And the definition is not rewritten or copied to user scope

    Scenario: Durable history resumes without promoting temporary context
      Given a disk-defined identity with its own previous private session
      When a caller starts that identity in the same project after stop
      Then a new incarnation resumes only that identity's private history
      And its tool grant cannot exceed the saved ceiling

    Scenario: Real durable execution keeps shared capabilities and project histories separate
      Given one disk identity granted read and write and two isolated project directories
      When a real Pi child in the first project appends a capability through agent_memory
      And writes an ordinary scratch file and a relative project file
      And the child is stopped and restarted in that project
      Then its private history, Memory entry and scratch content remain available
      And relative file operations use the parent's original project directory
      When the same identity starts in the second project after confirmed closure
      Then its Memory and scratch content are shared through its private identity home
      And the first project's conversation is absent from the second project's input
      And the first project's history and files remain unchanged

    Scenario: A newly authored definition cannot recover a former temporary conversation
      Given a stopped session-only child with no saved history
      When a user authors its canonical agent.md and starts the same name
      Then the new durable child starts private history without resuming temporary context

    Scenario Outline: Removed flags are refused before any effects
      Given a caller supplying <flag> with either boolean value
      When the start reaches schema validation or the handler
      Then the call is explicitly refused
      And no process, role, private data or definition is created

      Examples:
        | flag       |
        | persistent |
        | memory     |
        | worktree   |

  Rule: A disk name cannot select temporary amnesia

    Scenario: Saved identity outranks inline input and a published host
      Given a disk definition and a coordinator host
      When a caller starts that name with a different inline role
      Then the disk role and tool ceiling still apply
      And only the standalone owner starts and delivers that durable child

    Scenario: Parent shutdown closes execution without deleting data
      Given durable and temporary idle children
      When their parent shuts down
      Then both processes close
      And only the durable identity's private data remains for a later start

  Rule: List distinguishes processes from offline definitions without writes

    Scenario: Offline definitions are facts, not living handles
      Given disk definitions with no current process and a stopped incarnation
      When the caller lists children
      Then live and stopped sessions are separate from offline disk definitions
      And offline definitions expose scope, source, model and tools but no incarnation handle
      And discovery creates no directories or state
