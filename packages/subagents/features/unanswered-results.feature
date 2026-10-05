Feature: Settled execution without a usable final answer is explicit

  The execution layer reports what the child produced; it does not judge a
  review's correctness or invent a verdict. A settled empty message, provider
  failure, truncation or missing final message must not look like success.

  Scenario Outline: An authoritative unusable terminal message is reported once
    Given a prompted resident whose completed final message is <outcome>
    When the native sequence settles
    Then one unanswered follow-up identifies its Agent, exact incarnation and turn
    And it states the observed outcome and available stop reason
    And it preserves any original output bytes and bounded provider diagnostic
    And it says there is no usable final answer or acceptance verdict
    And the child stays IDLE and accepts later input without a replacement
    And repeated settles or planned closure do not duplicate that terminal notice

    Examples:
      | outcome                     |
      | empty or whitespace text    |
      | thinking-only output        |
      | provider error or abort     |
      | response length limit       |
      | unfinished tool-call output |
      | no completed assistant      |

  Scenario: An intermediate empty frame is not a terminal failure
    Given startup readiness or a stream settle without authoritative message evidence
    When a later frame carries the real final answer for that same sequence
    Then the intermediate frame consumes neither delivery nor unanswered state
    And the final answer returns once and verbatim

  Scenario: A valid complete answer does not gain a generated assessment
    Given nonempty final text with a successful stop and no unfinished tool call
    When execution settles
    Then the answer returns verbatim in the existing result envelope
    And no runtime PASS or acceptance verdict is added

  Scenario: Native final diagnostics survive parsing and later sequence reset
    Given message_end records stopReason, errorMessage and original text
    When agent_settled and a later agent_start share a pipe read
    Then the settled frame preserves its own diagnostics before reset
    And the next sequence starts without the prior failure or final-message metadata

  Scenario Outline: A later message cannot reuse earlier final-answer evidence
    Given one assistant message completed successfully in a running sequence
    When a later assistant message begins through <boundary> but never completes
    And that sequence then settles
    Then the latest output is unanswered with missing-final evidence
    And the prior stop reason and completed-message flag cannot make it successful
    And earlier final text is not concatenated into the new draft

    Examples:
      | boundary                 |
      | native message_start     |
      | content start event      |
      | streamed delta fallback  |

  Scenario: Unknown stop reasons are bounded across every result surface
    Given a final message carries an unrecognized arbitrarily long stop reason
    When it is parsed, classified, rendered or restored from message details
    Then the stop reason is normalized to a bounded unknown value
    And it cannot expand a summary or result envelope beyond the diagnostic budget
    And partial text remains unchanged and is not accepted as complete

  Scenario: Diagnostics do not leak unbounded provider payloads
    Given a provider error message exceeds the diagnostic preview budget
    When an unanswered notice is rendered or read from the roster
    Then the diagnostic is sanitized and bounded with an explicit truncation notice
    And the full final text bytes remain unchanged

  Scenario: Real native Pi exposes an empty review as an unanswered outcome
    Given an isolated local provider returns an empty or length-limited review
    When real parent Pi delegates and the RPC child settles
    Then the follow-up is nonempty and clearly identifies missing usable output
    And no blank result envelope, fabricated verdict or duplicate model retry appears
    And a later valid input uses the same resident and returns a normal answer
