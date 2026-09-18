Feature: Unassigned resident startup without execution
  Agent start creates presence, not Work. Later autonomous board acquisition remains supported.

  Scenario: Public start returns an unassigned resident without a model kickoff
    Given a pending Work Item and an inline Agent definition
    When the Leader awaits agent start and immediately assigns its exact returned session
    Then start has awaited the correlated native readiness acknowledgement
    And assignment succeeds without caller sleeps or readiness injection
    Then the receipt has no Work ID or Assignment Attempt
    And no prompt is sent merely to announce that there is no assignment
    And startup readiness is established without a model turn

  Scenario: Explicit assignment follows readiness without a speculative idle label
    Given an unassigned resident is starting
    When its native runtime acknowledges readiness
    Then the resident is idle and eligible for exact-session assignment
    When the Leader assigns the existing pending Work Item
    Then the same Work ID is claimed with a new Assignment Attempt
    And a fresh session receives its assigned prompt

  Scenario: Assigning the same exact current owner is idempotent
    Given the existing Work is claimed by the exact returned session
    When the Leader assigns that same Work to that exact session
    Then the receipt identifies the existing Assignment Attempt
    And no fresh session or second prompt is sent
    And other owners and stale session routes remain rejected

  Scenario: Later board notices still permit deliberate autonomous acquisition
    Given an unassigned idle resident and claimable Work
    When the harness delivers a valid board notice
    Then the Worker Work tool becomes active
    And a deliberate claim may acquire the pending Work through the existing authority guards
    And start does not promise permanent assignment-only scheduling

  Scenario: A non-ready acknowledgement is an observable startup failure
    Given an unassigned child is awaiting native readiness
    When its correlated acknowledgement is non-ready or rejected or times out
    Then the awaited start rejects with an actionable readiness error
    And Presence exposes an actionable readiness error instead of silently waiting forever
    And no model kickoff is fabricated

  Scenario: The first autonomous wake retains the Agent definition
    Given an unassigned resident started without a model kickoff
    When its first board notice or ordinary message wakes it
    Then its Agent role instructions accompany that wake
    And Work controls activate only for a valid assignment or board notice

  Scenario: Recovery transfers the same Work only after release settles
    Given an existing Work Item retains an active owner
    When the Leader asks that owner for read-only recovery through an ordinary message
    Then communication alone does not retire its authority
    And the Leader uses explicit Work release and waits for authoritative release before reassigning that same Work
    And recovery guidance does not recommend a duplicate delegate Work
