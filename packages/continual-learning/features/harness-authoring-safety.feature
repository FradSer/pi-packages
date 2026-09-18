Feature: Outcome-based harness authoring without speculative writes
  Scenario: Unsupported and ambiguous requests leave a missing target missing
    Given a project without harness configuration
    When the user requests an unsupported global semantic constraint or an ambiguous requirement
    Then /harness supplies the exact project shared target without creating any file or directory
    And authoring reads that target and assesses expressibility before considering a write
    And unsupported or ambiguous requests result in no file writes
    And recommending project AGENTS.md does not authorize editing it

  Scenario: A supported request writes one complete candidate
    Given an explicit request expressible as a skill, bash, or text rule
    When the author finishes assessing the request and reading the exact target
    Then it preserves unrelated rules and writes the complete valid candidate once
    And it never writes a preliminary empty configuration
    And it reads the same target back to verify persistence
    And trigger checks use non-executing evaluators or controlled fixtures, never dangerous commands
    And saved, resolved, delivered, and executed outcomes are reported separately

  Scenario: Invalid predecessors require an explicit user decision
    Given malformed rules, malformed legacy containers, or unknown fields in the target
    When a model proposes a complete harness write
    Then schema diagnostics preserve the predecessor bytes
    And replacement or repair requires explicit authorization through the native confirmation UI
    And headless requests fail closed rather than authorizing repair implicitly

  Scenario: Invalid layers can be repaired one at a time without implicit migration
    Given both the global and project shared harness files contain malformed configuration
    When a complete valid replacement is proposed for either invalid target
    Then the authoring prompt directs the model to submit a valid target-only repair for explicit native confirmation
    And unchanged diagnostics exclusively from other layers do not prevent its native confirmation preview
    And the preview reports the remaining incomplete activation without authorizing changes to other layers
    And headless, rejected, timed-out, or cancelled confirmation preserves every original byte
    And approval rechecks the target and other layer bytes before allowing the native write
    And the gate itself leaves every file untouched until the native write executes
    And the write result reports remaining diagnostics from the current effective configuration without replacing native output or becoming a text-rule trigger
    And Bash remains fail-closed after the first repair until the second unreadable layer is repaired
    And repairing the second layer requires its own explicit confirmation

  Scenario: Repair authorization is not a general validation bypass
    Given an invalid target and diagnostics in an unchanged other layer
    When a candidate has malformed JSON, invalid schema or regex, an unknown skill, or forged provenance
    Then the candidate is blocked before any confirmation or mutation even if a nearer layer shadows it
    And a write to a valid or missing target still requires a fully valid effective configuration
    And changes to the target or another layer during confirmation require fresh validation and authorization

  Scenario: Policies installed during configuration preflight govern the write
    Given a configuration write performs asynchronous path and predecessor checks
    When a valid legacy block or confirmation policy appears before the approval snapshot is captured
    Then policy evaluation uses the configuration after preflight rather than a cached earlier resolution
    And repair approval cannot bypass that policy
    And rejected calls leave the target and newly installed policy unchanged

  Scenario: Repair approval remains bound through a later policy confirmation
    Given a configuration repair was explicitly approved against exact predecessor bytes
    And a valid installed policy also requires confirmation for that write
    When the target or any other configuration layer changes during the later confirmation
    Then the native write is blocked even if resolved rules and diagnostics are unchanged
    And the concurrent file bytes remain untouched
    And unchanged approved files permit the native write after both approvals
    And raw-byte, exact-argument and cancellation checks run after the final asynchronous approval

  Scenario: Preserve the user's semantic boundary
    Given a request that fullscreen popup means an overlay relationship
    When authoring instructions are generated
    Then the request remains verbatim and no opacity, input, or scroll restriction is added
    And the generic prompt requires scope preservation and clarification rather than embedding that anecdote

  Scenario: Project configuration is the default
    Given a rule request with no scope flag
    When /harness resolves its target
    Then it selects .pi/harness.json
    And --local explicitly selects .pi/harness.local.json
    And --global selects the user shared harness.json and never user harness.local.json
    And symlinked target files or parent paths are rejected before any mutation
