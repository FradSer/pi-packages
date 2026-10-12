Feature: Safe task recovery and retained lifecycle evidence
  Scenario: Recovery reasons obey the retained byte budget
    Given a blocked task with retained failure evidence
    When the caller takes it with an oversized recovery reason
    Then the take is refused without changing the task or its lease

  Scenario: Success requires recovery before delivery
    Given a blocked task after a failed attempt or operational blocker
    When the caller uses update_task to deliver success without a recovery take
    Then delivery is refused even for the creator
    When the caller takes it with a safe recovery reason
    Then successful delivery is available

  Scenario: Successive attempts retain earlier evidence
    Given a task with successive failures and operational blockers
    When it resumes and the runtime stops its holder
    Then earlier failure and blocker evidence remains in byte-budgeted evidenceHistory
    And an oversized normal write is refused
    And runtime cleanup releases the holder even for oversized legacy content

  Scenario: A failed retry retains an earlier verified result
    Given a completed task with an exact verified result
    When update_task reopens it and records a failed retry
    Then get_task returns the earlier result in evidenceHistory
    And runtime cleanup also retains a prior legacy result

  Scenario: Outstanding work describes the current remainder
    Given a handoff with prior findings and outstanding work
    When the caller supplies replacement outstanding work or an empty list
    Then outstanding work is replaced or cleared
    And prior findings remain additive

  Scenario: A present malformed task file never becomes a writable empty store
    Given a valid JSON task file without a valid tasks map
    When the session starts and a task is created
    Then the read reports an error and the original file stays unchanged
    And valid completed records and legacy recovery evidence remain readable
