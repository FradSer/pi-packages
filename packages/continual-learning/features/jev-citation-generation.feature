Feature: Evidence-complete Memory generation and bounded semantic repair
  Scenario: Current-state and verified-result facts require relevant original citations
    Given a frozen dossier contains future instructions and actual verification
    When a Memory candidate is generated or semantically repaired
    Then guidance distinguishes intended future use from verified current state
    And every body and description claim cites its relevant original source
    And later corrections and exceptions are preserved without citing unrelated entries

  Scenario: Existing parent authority remains decisive
    Given missing, sensitive, oversized or contradictory evidence
    When the one existing read-only repair is requested
    Then guidance forbids invented evidence and unverified success claims
    And exact quote validation, privacy, retained candidate identity and full Jev checks still decide application
    And unavailable Jev does not consume a new repair or release Harness constraints

  Scenario: The repair schema demonstrates a grounded index description
    Given a rejected Memory needs a read-only repair
    When the repair worker receives its schema example
    Then the example description repeats a concrete fact from its example body
    And the example cannot serve as evidence for a real candidate

  Scenario: Complete review fits by lossless transmission instead of dropping source
    Given complete evidence exceeds the preferred window partition count
    When adjacent whole-entry windows fit the actual encoded request and batch bounds
    Then at most sixteen windows retain every original entry and later correction
    And every request remains within the unchanged sixty-four-thousand-byte bound

  Scenario: Original citation text is already present in the same support request
    Given an exact long quote occurs in its indexed source with the same role
    When the wire state replaces only the duplicate quote with a smaller bound reference
    Then the complete original source and quote digest reconstruct the exact quote
    And unrelated indexes or mismatched roles never supply a reference

  Scenario: A later verification result is reviewed outside its invocation window
    Given an uncited tool result has a unique earlier matching invocation
    And whole-entry windowing separates that invocation from its result
    When Memory counterevidence is reviewed
    Then the result's review request includes the exact invocation and original indexes
    And invocation arguments are context rather than verified outcomes or authorization
    And duplicate identifiers or mismatched tool names never supply provenance

  Scenario: Complete source review misses a contradictory Memory body
    Given a real generated Memory passes source review but contradicts itself
    When independent no-tool body review identifies exact conflicting body spans
    Then the parent holds the candidate and uses the existing bounded correction opportunity
    And corrected content must pass fresh body and complete source review before application
    And body review never substitutes for source truth or grants write authority

  Scenario: Independent body review is incomplete or unavailable
    Given a missing, stale, malformed, interrupted or oversized body judgment
    When source review would otherwise allow the Memory
    Then the Memory remains held without silently accepting or inventing a correction
    And every attempted body-review call retains its usage and unknown-cost status

  Scenario: Independent consistency requests exceed the combined body budget
    Given several complete bodies fit individually but exceed 64000 bytes together
    When independent body consistency is reviewed
    Then requests split only between complete targets before the first call
    And every attempted group retains its own cost including a later interruption
    And an individually oversized body is refused without truncation or calls

  Scenario: Body consistency is separate from original source support
    Given source support and complete candidate content exceed one combined request
    When the internal consistency question is sent separately
    Then it receives the exact complete candidate body or its bound same-state reference
    And source support and counterevidence still receive their complete original context
    And every request and the complete review obey the existing bounds

  Scenario: A real body reviewer corrupts a copied target digest
    Given a retained actual JSON response changed the parent target identifier
    When the worker instead selects immutable request-local integer target slots
    Then the parent restores identities and body hashes from the complete request
    And duplicate, foreign or noninteger slots and model-generated digest fields are rejected
    And a valid selection still does not prove a correct semantic judgment

  Scenario: Normal project learning delegates request capacity to the configured service
    Given complete frozen evidence contains an entry larger than the historical 64000-byte cap
    When normal project Memory review runs without an explicit experimental byte bound
    Then the complete evidence reaches the configured service without truncation
    And final revocations still veto application at the unchanged semantic thresholds
    And service failures retain the proposal and all known usage
    And historical bounded experiments can explicitly retain their original byte bound

  Scenario: Empty source lines remain visible but are not generation choices
    Given frozen source text contains empty or whitespace-only lines and chunks
    When the parent renders citation labels and the structured-output domain
    Then all original text and line positions remain available
    And empty or whitespace-only fragments have no selectable reference label
    And meaningful ranges preserve intervening whitespace
    And legacy range endpoints remain compatible with unchanged citation gates
