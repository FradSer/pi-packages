Feature: Native learning history and restoration in a disposable project
  Scenario: Undo every applied phase through the real Pi menus
    Given an isolated project, HOME and agent directory with recorded predecessor files
    When real Pi learns Memory and Harness through a deterministic loopback provider
    Then the visible result agrees with persisted applied receipts and history
    When I inspect each change in Recent learning and cancel its native undo confirmation
    Then no learned file changes
    When I confirm each undo through the same native interface
    Then history retains each change as undone
    And all learned surfaces match their predecessor bytes, permissions and absence
    And unrelated project files and the original receipt remain unchanged

  Scenario: Mirrored learning keeps its result visible in the history list
    Given a Memory change tracks the same index and body on private and public surfaces
    When I open Recent learning in a 48-column terminal
    Then the target summary contains no duplicate names
    And its applied or undone status remains visible
    And full paths remain available in the detail reader

  Scenario: A live acceptance run is isolated and immutable
    Given a disposable project and an explicit loopback or real-model mode
    When acceptance starts
    Then validate effective settings, environment and provider before launching Pi
    And freeze source hashes and create a new private evidence directory
    When any source changes or a stale dialog result is observed
    Then acceptance fails without replacing earlier evidence
    And generate the manifest and gallery even after failure

  Scenario: Learning records are grouped by exact pipeline identity
    Given multiple mutations from one learning pipeline and an older ungrouped record
    When I inspect Recent learning
    Then the pipeline mutations share a read-only batch overview
    And the older record remains accessible without guessed grouping
    And index preparation is distinguished from learned knowledge
    And undo still requires inspecting and confirming one exact change
