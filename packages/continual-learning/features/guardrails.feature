Feature: Flat layered Harness rules with installed-policy compatibility
  Scenario: Three layers resolve exact ids by nearest complete replacement
    Given global, project shared and project personal harness.json files
    When the runtime resolves rules
    Then distinct ids independently inherit and nearer same-id definitions fully replace outer definitions
    And enabled false shadows rather than deleting the identity
    And obsolete user-personal and project .pi/agent files are not read
    And current file bytes are checked even when timestamps have not changed

  Scenario: Compatible legacy data is not a structural configuration failure
    Given valid installed policies, disabled names and skillPrompts or an empty configuration
    When the runtime loads that file
    Then its original protections and delivery semantics remain active
    And compatible format notices do not block unrelated tools
    And all configuration bytes remain unchanged

  Scenario: Structurally ambiguous files retain conservative diagnostics
    Given unknown roots, malformed containers, duplicate flat ids or missing flat identities
    When the runtime loads that file
    Then it diagnoses the unsupported structure without modifying any bytes
    And a previously unambiguous snapshot may be reused with an explicit stale diagnostic
    And without a snapshot execution remains incomplete
    And exact configuration diagnosis and authorized repair remain available subject to valid policies

  Scenario: Invalid identity winners do not revive outer definitions
    Given an invalid rule with a recognized id
    When the rule wins the nearest layer
    Then valid independent siblings remain available
    And invalid Bash or ambiguous selectors hold Bash calls pending repair
    And invalid skill or text declarations affect their own guidance rather than arbitrary tools

  Scenario: Bash match messages accompany the single execution decision
    Given several rules match the same model-originated Bash command
    When any rule blocks the command
    Then Bash remains unexecuted and every matching message is returned
    When rules require confirmation without any block
    Then one bounded native confirmation asks about that call and all its reasons
    And refusal, expiry and missing UI remain unexecuted
    When matching rules omit action or the user approves once
    Then guidance accompanies the actual result without changing native output, errors or details
    And duplicate result hooks do not duplicate guidance

  Scenario: Built-in security gates survive compatible schema upgrades
    Given no user configuration
    When the model proposes interactive login, OTP routing, or bulk deletion of project or private Pi Memory
    Then the supported Bash gate blocks it with corrective guidance
    And ordinary commands and unrelated cleanup remain available
    And fixtures verify decisions without executing destructive commands

  Scenario: Configuration writes remain an internal integrity gate
    Given a native write or edit targets one of the canonical harness files through any native path alias
    When the complete JSON is malformed or names an unknown skill
    Then the write is blocked and edit requests require a complete validated write
    And parent-owned learnedRules metadata cannot be forged or removed
    And symlinked files or parent paths are rejected
    And invalid predecessor repair requires explicit native UI authorization
    And existing compatible policies still protect their configured write and read scopes

  Scenario: Status distinguishes flat rules, compatible legacy declarations and diagnostics
    Given active, disabled, invalid or unavailable rule identities
    When /harness runs without a request
    Then it reports identity, selector, action, state, source and canonical paths
    And compatibility notices are distinct from invalid configuration errors
    And incomplete or stale loading is not reported as successful verification

  Scenario: Harness guidance remains separate from execution interception
    Given flat skill or text rules
    When the harness-guidance adapter prepares the next generation
    Then those rules provide retained guidance
    And the guardrails adapter combines flat Bash decisions with installed legacy policy checks and configuration integrity gates
