Feature: Resident RPC transport preserves answers and acknowledges control

  The execution layer owns one child's byte stream and control acknowledgements.
  A writable pipe is not proof that Pi accepted a prompt, and a diagnostic tail
  is not the child's final answer. No task storage or team runtime is involved.

  Rule: Final answers remain verbatim while previews and hostile input are bounded

    Scenario: A long answer settles in the same read as the next run starts
      Given a resident produces an answer longer than the live preview cap
      When its authoritative message, agent_settled, and the next agent_start share one read
      Then the finalResponse update contains the complete answer including surrounding whitespace
      And ordinary nonfinal previews remain bounded

    Scenario: UTF-8 code points span pipe reads
      Given assistant text contains multibyte characters and Unicode line separators
      When stdout splits a character across reads and frames records only on LF
      Then progress and the final answer retain every original character

    Scenario: An authoritative whitespace-only message replaces a streamed draft
      Given the assistant streamed draft text
      When message_end contains only whitespace
      Then both the settled update and the public parser return that whitespace verbatim

    Scenario: Close follows enough unrelated records to evict the diagnostic tail
      Given a resident already completed a long final answer with usage
      When unrelated records exceed the diagnostic-tail capacity and another run starts
      And the child closes before that next run completes
      Then onExit stdout is the last authoritative complete answer
      And onExit usage includes the lifetime usage, not just surviving tail records

    Scenario: A completed assistant message closes before a settle event
      Given message_end replaced a streamed draft with the authoritative answer
      When the child closes before agent_settled
      Then onExit stdout is the complete authoritative message, not the draft

    Scenario: A final JSONL record closes without a line terminator
      Given the child writes message_end and agent_settled without a trailing LF
      When the child closes
      Then the final answer and settlement are parsed before onExit
      And all UTF-8 bytes in the answer are preserved

    Scenario: A close-time result may synchronously start a same-name successor
      Given the old resident has completed three turns
      When its close-time final update starts a successor with the same name
      Then the successor starts with a fresh turn baseline
      And its first result reports turn 1
      And old close cleanup cannot overwrite the successor stream state

    Scenario Outline: An input exceeds a hard per-record or per-message quota
      Given a resident receives <input>
      When the relevant hard byte quota is exceeded
      Then termination is requested and a bounded diagnostic names the quota
      And no partial answer is reported as a successful process result
      Examples:
        | input                            |
        | one oversized JSONL line         |
        | one oversized unterminated line  |
        | streamed assistant message text  |
        | streamed assistant thinking      |
        | streamed tool-call arguments     |
        | one authoritative message        |

    Scenario: Many individually bounded messages exceed a lifetime quota
      Given each assistant message and JSONL record stays below its hard byte quota
      When a resident completes enough messages to exceed those quotas in aggregate
      Then the child remains live and usage accumulates across messages

  Rule: Private history candidates are regular unlinked files

    Scenario: Resume refuses a jsonl symlink before spawning
      Given a private session directory has a link to valid outside history
      When spawnResident requests resume
      Then no operating-system child starts
      And the linked history is not read or appended

  Rule: Prompt-less startup waits for the already issued native idle handshake

    Scenario Outline: Cold startup may outlast an ordinary control deadline
      Given a new Pi process is still loading for more than five seconds
      When its <startup> acknowledgement arrives within thirty seconds
      Then startup succeeds for that exact child
      And the startup command is written once without a model retry
      Examples:
        | startup             |
        | initial prompt      |
        | idle readiness      |
        | fork context setup  |

    Scenario: Cold startup has a bounded confirmation window
      Given the initial prompt of a new child has no acknowledgement
      When its thirty-second startup window expires
      Then acceptance reports uncertainty
      And a late acknowledgement does not confirm the expired request

    Scenario: A running resident retains its ordinary control deadline
      Given native startup has confirmed an idle child
      When a later prompt has no acknowledgement for five seconds
      Then delivery reports uncertainty without repeating that prompt

    Scenario: Fork kickoff uses the ordinary deadline after context setup
      Given fork context setup is acknowledged after more than five seconds
      When the subsequent kickoff has no acknowledgement for five seconds
      Then kickoff reports uncertainty without repeating the prompt
      And a late kickoff acknowledgement does not revive the expired request

    Scenario: Cancellation and replacement retain exact child control ownership
      Given startup input was dispatched
      When its caller cancels waiting
      Then the original session remains starting without repeating its prompt
      When that exact session is stopped and its child confirms closure
      And a same-name successor starts
      Then late acknowledgements and closure from the old child cannot change the successor
      And only the successor acknowledgement confirms its startup
      And subsequent input is written once to the successor

    Scenario: Idle startup is acknowledged synchronously
      Given a prompt-less spawn receives an immediate idle get_state response
      When the caller awaits SpawnedResident.readiness or waitForResidentReady
      Then both observe the same successful handshake without sending another command

    Scenario Outline: Startup is not acknowledged idle
      Given a prompt-less resident is awaiting get_state
      When startup <outcome>
      Then readiness resolves false rather than claiming an idle child
      Examples:
        | outcome                     |
        | is rejected                 |
        | reports streaming           |
        | reports compaction          |
        | reports pending messages    |
        | closes                      |
        | times out                   |
        | cannot write the command    |

    Scenario: Existing prompted startup stays immediate
      Given a spawn includes a nonempty description
      When it starts
      Then the description is written once and no idle readiness handshake is imposed

  Rule: Resident prompt delivery reports the actual correlated RPC outcome

    Scenario: Acceptance and a complete answer arrive inside the stdin write
      Given an idle resident has completed startup
      When deliverResidentPrompt receives a synchronous prompt response and final stream
      Then its pending response was registered before the write
      And acceptance resolves true without clearing or losing the completed answer

    Scenario Outline: Prompt delivery resolves from the control response
      Given an idle resident is sent a uniquely identified prompt
      When the child <outcome>
      Then delivery resolves <accepted>
      And a handled input does not fabricate a settled answer
      And an unknown timeout retains input authority until inspected or stopped
      Examples:
        | outcome                              | accepted |
        | acknowledges started                 | true     |
        | acknowledges queued                  | true     |
        | acknowledges legacy success          | true     |
        | acknowledges handled                 | false    |
        | rejects the command                  | false    |
        | closes before acknowledgement        | false    |
        | never acknowledges before timeout    | unknown  |
        | has an unwritable control stream     | false    |
        | throws during the control write      | false    |

    Scenario: A mismatched response arrives before the real prompt response
      Given a resident prompt is awaiting its request id and prompt command
      When a different id or command is acknowledged first
      Then delivery remains pending until its own prompt response arrives

  Rule: Public steering acknowledges native input without resetting the sequence

    Scenario: A steer waits for its own prompt response
      Given a working native child with a turn in flight
      When deliverResidentSteer writes a steer command
      Then acceptance remains pending until its correlated RPC response
      And rejection or closure returns false
      And a wrong command or request id does not consume acknowledgement
      And a timeout reports uncertainty instead of successful steering
      And the current streamed answer and turn baseline are unchanged

  Rule: Duplicate installed module roots operate the same resident by identity

    Scenario: A second module root controls a child spawned by the first
      Given two independently loaded spawner module roots in one process
      When one starts a resident and the other awaits readiness, prompts, steers, and terminates it
      Then both operate the exact same child and pending control state
      And the legacy fresh-assignment and follow-up paths remain available

    Scenario: An old process closes after its replacement started
      Given an old child and a replacement child share an agent name
      When the old child closes after the replacement completed its first turn
      And a new prompt is delivered to the replacement
      Then the replacement's stream state and turn baseline are preserved
      And its readiness and prompt acknowledgements are not removed by the old close
