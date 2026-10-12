Feature: End-to-end BDD verdict
  The package reads a Gherkin .feature scenario and one run evidence file, then
  reports whether the scenario was fulfilled. Clauses with a declared check are
  decided in code. Only the remaining clauses are sent to the TypeSafe Jev model.
  Policy, gates, and the final verdict stay in code, never in the model.

  Background:
    Given the e2e package is installed
    And a scenario has Then clauses and a run evidence file

  Scenario: Deterministic checks decide the clauses that declare them
    Given a run evidence file declares a check for Then clause 1
    And that check compares an observed value against an expected value
    When the package verifies the scenario
    Then clause 1 is decided in code from the observed value
    And no question is sent to Jev for clause 1

  Scenario: Remaining clauses become narrow independent Jev questions
    Given a run evidence file declares no check for Then clause 2
    When the package verifies the scenario online
    Then clause 2 is asked as its own yes or no question
    And the scenario verdict and the business severity are asked in the same request
    And the request carries the scenario text and the run evidence as state

  Scenario: The final verdict comes from code, not from the model
    Given the model answers a verdict choice and a severity score
    When the model verdict probability is below the verdict gate
    Then the composed verdict is needs_review
    And the policy reports the gate that decided the outcome
    And a deterministic failure overrides a fulfilled model verdict

  Scenario: A clause without evidence stays unverified
    Given no check and no model answer covers a Then clause
    When the package verifies the scenario offline
    Then that clause is reported as unjudged
    And the composed verdict needs review instead of claiming fulfillment

  Scenario: The report names the verdict, the clauses, and the source of each answer
    Given a verification finished with mixed clause outcomes
    When the package renders the markdown or HTML report
    Then the report lists every Then clause with its status and its source
    And the report states how many clauses are still unjudged
    And the HTML report marks the verdict and each clause row with a stable test id

  Scenario: The CLI keeps CI exit codes stable
    Given a fulfilled scenario
    When the CLI verifies it
    Then the CLI exits with code 0
    And an unfulfilled scenario exits with code 1
    And a scenario that needs review exits with code 2

  Scenario: The pi extension exposes the same verification as a command
    Given the extension is loaded
    When the user runs /e2e with a feature and an evidence path
    Then the extension runs the same core and notifies the verdict
    And the extension never asks for or stores a model credential

  Scenario: The extension injects a stable e2e capability note directly after the system prompt
    Given the e2e extension is loaded in Pi
    When the session prepares its transcript for a provider turn
    Then the harness injects a stable capability note at index 1
    And the note teaches the model when and how to call e2e_verify

  Scenario: The extension provides an autonomous e2e_verify tool
    Given the e2e extension is loaded in Pi
    When the agent loop executes an e2e_verify tool call
    Then the tool runs the three-layer verification engine
    And the tool returns structured verdict data with clause breakdown

  Scenario: A feature directly involved in the current turn starts the acceptance workflow
    Given the agent touches a .feature path or names an explicit .feature path in a shell command
    And the user may explicitly request acceptance for a .feature path without changing files
    When the agent attempts to settle without matching fulfilled verification
    Then the harness continues the turn with an acceptance checkpoint
    And implementation file activity only invalidates a feature already involved in this turn
    And the checkpoint directs the agent to inspect the project and existing tests
    And the checkpoint requires real test results as evidence before e2e_verify
    And the checkpoint forbids invented evidence or a claimed pass without verification
    And the checkpoint stays active until each requested scenario in the feature is fulfilled

  Scenario: An explicitly requested feature starts acceptance without edits
    Given the user explicitly names a .feature path for acceptance
    When the agent attempts to settle without a matching fulfilled verification
    Then the harness continues the turn for that named path

  Scenario: A generic acceptance request retains partially verified features
    Given the user requests e2e without naming a feature path
    And a fresh run passes only one scenario in a feature with multiple scenarios
    When the agent attempts to settle
    Then the remaining scenarios are named in a bounded checkpoint

  Scenario: Relevant implementation repairs invalidate previous acceptance
    Given a package feature passed a fresh verification in this turn
    When the agent edits an implementation file in that same package
    Then its previous acceptance is withdrawn until a fresh run passes
    And unrelated package edits do not withdraw that feature

  Scenario: An unrelated parallel feature change does not start acceptance
    Given a .feature file changes in another package
    And that package and feature path are not involved in this turn
    And the user did not name that path for acceptance
    When the agent attempts to settle
    Then the harness does not continue for the unrelated feature

  Scenario: The same checkpoint is not repeated without new progress
    Given the harness already returned a checkpoint for the current feature and verification state
    When the agent settles again without new tools or verification results
    Then the harness does not repeat that checkpoint
    And unrelated reads and searches do not count as progress
    And a new relevant mutation or verification result permits another bounded correction

  Scenario: Feature acceptance continuations stop at the configured bound
    Given the agent changes a .feature file and does not produce verification evidence
    When the agent reaches the maximum automatic continuations
    Then the harness stops continuing and leaves the result unverified

  Scenario: A fulfilled verification for the changed feature clears its checkpoint
    Given the agent changes a .feature file
    And the agent verifies that same file with a fulfilled verdict from a fresh configured runner
    When the agent attempts to settle
    Then the harness does not continue for that feature

  Scenario: A new user turn clears feature changes from the prior turn
    Given the agent changed a .feature file during a prior turn
    When the user starts a new turn
    Then the prior feature change does not trigger an acceptance checkpoint

  Scenario: The harness gate intercepts settlement when an unfulfilled verification was recorded
    Given a scenario verification that resulted in not_fulfilled or needs_review
    When the agent attempts to settle
    Then the harness gate intervenes before settlement
    And the harness returns a continuation checkpoint requiring the failure to be resolved

  Scenario: Caller-supplied fulfilled evidence cannot clear feature acceptance
    Given a changed feature and inline or pre-existing evidence
    When e2e_verify returns fulfilled without executing a fresh test run
    Then the changed feature checkpoint remains active
    And the result identifies the evidence as unverified

  Scenario: A fresh successful runner can clear feature acceptance
    Given a changed feature with all scenarios covered by tests
    When e2e_verify executes the project runner and reads its newly generated evidence
    Then only fulfilled scenarios backed by that successful run clear the checkpoint
    And failed aborted timed-out or missing-evidence runs cannot clear it
    And changes to the feature during the run or evaluation invalidate the evidence

  Scenario: Failed verification preserves changed-feature inspection directions
    Given a changed feature and a failed verification in the same turn
    When the agent attempts to settle
    Then one bounded checkpoint includes changed feature paths and the failed verdict
    And it requires inspection of project instructions scripts test setup and existing tests
    And it requires a fresh real run before verification

  Scenario: Verification can be retried after repairs in the same turn
    Given a failed verification or a changed project adapter in the current turn
    When the implementation or tests are repaired and e2e_verify is called again
    Then it captures the current project runner and executes a fresh test process
    And a fresh fulfilled result clears the previous failed scenario
    And manual verification calls are not limited by automatic continuation allowance

  Scenario: A later runner error withdraws the earlier pass
    Given the current scenario previously passed with fresh evidence
    When another verification attempt fails to execute or produce valid evidence
    Then the earlier pass cannot certify the current acceptance request
    And repairing the execution blocker and rerunning can pass in the same turn

  Scenario: Trusted adapters stay stable within each verification attempt
    Given the project runner configuration and adapter files were captured for one verification
    When the configuration or an adapter changes during that attempt
    Then the tool rejects that attempt without accepting its evidence
    And accepted evidence is invalidated if an adapter changes after verification

  Scenario: Canceling a turn does not emit a redundant acceptance warning
    Given unverified feature work in the current turn
    When the user aborts the run
    Then no automatic continuation or final acceptance warning is added
    And cancellation does not count as verified evidence

  Scenario: Read-only review does not request acceptance execution
    Given the user explicitly asks not to run e2e for a feature
    When the input hook prepares the turn
    Then no missing-verification checkpoint is generated

  Scenario: Default tool results keep complete failure diagnostics
    Given long verification errors or scenario reports
    When the tool renders in a narrow terminal
    Then the complete default result wraps without expansion or truncation

  Scenario: Stale asynchronous work cannot authorize a new turn
    Given a runner or feature snapshot is awaiting filesystem operations
    When a new input or reset changes the turn generation
    Then old work cannot replace the new turn snapshot or clear its checkpoint
    And a stale native runner is rejected immediately before process spawn

  Scenario: Every requested run remains fresh until settlement
    Given a fresh fulfilled verdict for an unchanged feature requested by the user
    When its adapter changes before settlement
    Then the accepted proof is withdrawn and verification remains pending

Feature: Simple and actionable acceptance feedback

  Scenario: Partial verification names the remaining scenarios
    Given a feature with two scenarios and a fresh pass for only the first
    When acceptance is checked before settlement
    Then the remaining scenario name is shown
    And the successful scenario is not requested again

  Scenario: A complete verified report needs no duplicate success notification
    Given every scenario has a fresh fulfilled verdict
    When the agent settles
    Then acceptance is complete
    And no redundant success notification is emitted

  Scenario: A plain git status does not revoke fresh acceptance
    Given a feature has fresh fulfilled acceptance
    When the agent reads git status without changing files
    Then acceptance stays complete
    When another shell inspection leaves the declared inputs unchanged
    Then acceptance stays complete
    When a shell command changes a declared adapter input
    Then freshness revalidation withdraws acceptance
    When an unknown shell program could change unlisted application inputs
    Then acceptance is conservatively revoked

  Scenario: Missing evidence asks for observations rather than speculative repairs
    Given a fresh run with unjudged clauses
    When the acceptance checkpoint is emitted
    Then it requests missing observations or checks
    And it does not require an implementation change merely because evidence is missing

Feature: Project adapter observation producers

  Scenario: Goal seed checks come from the real command handler
    Given a fresh session with no goal and a registered goal seed observation producer
    When the project adapter runs the goal seed scenario
    Then each Then clause has checks over actual command observations
    And the producer is included in the trusted adapter files
    And passing linked tests alone cannot fabricate those observations

Feature: Settlement checkpoint suppression

  Scenario: Repeated settlement refresh does not spend another continuation
    Given unresolved acceptance has already received a checkpoint
    When settlement refresh finds no new changes or results
    Then no duplicate checkpoint is emitted
    And the remaining continuation is preserved for actual progress

Feature: Actionable runner errors

  Scenario: A failed runner reports its bounded diagnostics
    Given the project runner prints a useful failure diagnostic
    When it exits with a nonzero code
    Then the tool reports the exit code and diagnostic
    And no successful proof is created

Feature: Consistent terminal feedback

  Scenario: Status headers contain only the package and readable state
    Given native verification or a manual e2e command
    When progress or a result is displayed
    Then the header contains only e2e and the readable status without a separator or subject
    And feature scenario evidence and recovery information appear in the body

  Scenario: Verification phases update one running result
    Given an authorized fresh runner for a feature with multiple scenarios
    When the native tool executes and evaluates its evidence
    Then running updates identify the current verification phase
    And a passed result reports the feature acceptance count and remaining scenarios

  Scenario: Supplied passes do not look like verified acceptance
    Given caller-supplied evidence that fulfills every clause
    When its verdict is displayed
    Then the header says needs review while the machine verdict remains fulfilled
    And the evidence source and fresh-run requirement precede the clause list

  Scenario: Provider blockers remain visible in default results
    Given a semantic clause and an unavailable provider
    When verification returns needs_review
    Then its default body includes the actual provider error and recovery action
    And it uses warning feedback rather than a business-failure style

  Scenario: Settlement waiting identifies unfinished work
    Given acceptance still has unverified scenarios
    When automatic continuation cannot proceed
    Then the waiting body names remaining work and the next action
    And a repeated unchanged settlement does not repeat the message

Feature: Verification intent and efficient acceptance

  Scenario: Behavior-preservation constraints do not cancel verification
    Given a request forbids changing behavior just to pass tests
    And it explicitly requests fresh verification of acceptance.feature
    When the gate records the request
    Then an unverified requested feature receives a settlement checkpoint

  Scenario: Explicit execution prohibitions remain respected
    Given the user explicitly forbids running acceptance tests
    When the gate records the request
    Then it does not request a verification run

  Scenario: Verification is planned before the final budget boundary
    Given the E2E capability is injected into a coding session
    When the agent plans tests for an authorized acceptance adapter
    Then guidance requests early focused fresh verification without duplicate suite execution
    And guidance distinguishes scenario coverage from complete request acceptance

  Scenario: Failed fresh evidence carries adapter diagnostics to repair
    Given a runner exits successfully while recording unmet checks
    When e2e_verify reads the fresh evidence
    Then bounded stdout and stderr accompany the unmet verdict as diagnostic data
    And the diagnostics cannot mint fulfilled acceptance

  Scenario: Verification guides a complete repair without repeated unproductive checks
    Given a public request with several requirements and a configured runner
    When the agent plans acceptance and receives verification diagnostics
    Then it maps each requirement to an observable check and labels missing coverage
    And it repairs observed defects and verifies the final changed code again
    And it stops repeated unchanged checks with an explicit remaining limitation
Feature: Complete coverage and actionable evidence
  Scenario: Verify every scenario without silently accepting the first
    Given a feature with multiple scenarios and an authorized scenario-aware adapter
    When verification requests all scenarios
    Then every scenario has its own fresh result and coverage entry
    And any failed or missing scenario prevents overall acceptance

  Scenario: Separate a counterexample from missing evidence
    Given a check with an expected value and a source location
    When the observed value differs
    Then the report identifies the path, expected value, observed value and location
    And fresh deterministic counterexamples request code repair
    But missing observations and uncertain semantic judgments request evidence collection


  Scenario: Preserve shipped Python assertions in a trusted adapter
    Given original tests assert complete messages and exact error identities
    When candidate tests replace them with argument-only or prefix-only checks
    Then the preservation guard reports the original test location and expectation
    And added tests cannot compensate for removing an original assertion
