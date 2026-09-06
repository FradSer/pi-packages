Feature: A unified design capability in Pi
  Impeccable procedures use one concern-organized taste library.
  Loading guidance does not authorize edits or execute scripts.

  Scenario: Context reads the target project rather than the package
    Given a target project with PRODUCT.md and DESIGN.md in a path containing spaces
    When packaged context runs from that project
    Then it reports that project's product and design context
    And it does not use the package directory as the project

  Scenario: Empty project context is actionable and isolated
    Given an empty target project and an isolated home directory
    When packaged context runs
    Then it reports missing context without pretending context was found
    And it does not check for upstream updates or write global cache files
    And it does not advertise unavailable scripts or authorize subagents

  Scenario: Monorepo context honors explicit target selection
    Given a monorepo with multiple application contexts
    When context runs with an explicit application target
    Then it selects the matching application context
    And an unresolved target is not reported as a successful selection

  Scenario: Static detector reports real findings
    Given a local HTML fixture violating a stable detector rule
    When the packaged detector runs with JSON output
    Then it returns a findings array containing that rule
    And it exits with code 2 for primary findings
    When the packaged detector examines a clean local HTML fixture
    Then it returns an empty findings array and exits with code 0

  Scenario: Missing native guidance is not disguised as support
    Given target context identifies a native platform
    And its canonical platform supplement is unavailable
    When packaged context runs
    Then it reports the unavailable platform guidance explicitly
    And it does not read excluded upstream native documents
    And it does not substitute web guidance as native guidance

  Scenario: Detector style suggestions do not override canonical taste
    Given a local fixture triggers an upstream stylistic rule
    When the packaged detector reports that suggestion
    Then it classifies the stylistic finding as advisory
    And it does not fail solely because of that stylistic suggestion
    And findings are not presented as proof of accessibility conformance

  Scenario: Static detector does not acquire browser capabilities
    When the detector is invoked with a URL or without an explicit local target
    Then it returns an actionable unsupported-mode diagnostic
    And it does not discover a development server or download a browser

  Scenario: Command and model load the same polish guidance
    Given polish requires principles and component guidance
    When the user invokes polish with a target request
    And the model loads polish
    Then both receive the same canonical procedure and required topics
    And the command preserves the target request verbatim
    And each required topic appears once

  Scenario: Load a disclosed motion reference
    Given polish discloses motion guidance
    When the model requests that reference through polish
    Then package paths are resolved in the returned content
    And unrelated references are not loaded

  Scenario: Every disclosed canonical link can be loaded
    Given any implemented capability has loaded its required guidance
    When that guidance links to another canonical taste reference or internal procedure
    Then the target is reachable through that capability's loader graph
    And reference loading accepts links containing anchors or URI prefixes
    And conditional cross-topic guidance does not create mandatory dependency cycles

  Scenario: Reject references outside the capability graph
    Given a reference is not reachable from polish
    When the model requests that reference through polish
    Then loading fails with an actionable diagnostic

  Scenario: Headless invocation without a capability
    Given Pi has no interactive UI
    When impeccable is invoked without arguments
    Then it returns explicit usage without opening a dialog

  Scenario: Select an implemented capability from the menu
    Given Pi has an interactive UI
    When the user selects polish from the impeccable menu
    Then the polish guidance is sent as one follow-up request
    And no script executes as a side effect of selecting guidance

  Scenario: An explicit user can load a command-owned capability
    Given an implemented capability requires an explicit user action
    When the user invokes that capability through the impeccable command
    Then its guidance is sent as one follow-up request
    And the same capability remains unavailable through the model loader

  Scenario: Cancel the capability menu
    Given Pi has an interactive UI
    When the user cancels the impeccable menu
    Then no follow-up request is sent

  Scenario: Unknown capability does not fall back
    When impeccable is invoked with an unknown capability
    Then it reports the unknown capability without loading a default

  Scenario: Explicit-user actions remain command-owned
    Given a capability requires an explicit user action
    When the model tries to load that capability
    Then loading is rejected
    And no script runs and no follow-up is sent

  Scenario: Invalid catalog edges fail before loading
    Given a capability requires or discloses an unknown resource
    When the catalog is validated
    Then validation identifies the invalid edge
    And no partial guidance is returned

  Scenario: Cyclic required dependencies fail before loading
    Given required resource dependencies form a cycle
    When the catalog is validated
    Then validation identifies the cycle
    And loading does not recurse indefinitely

  Scenario: Resources cannot escape the installed package
    Given a catalog resource resolves outside the installed package
    When the resource is loaded
    Then loading rejects the resource path
    And no outside file content is returned

  Scenario: Loader rendering remains bounded
    Given a loader result contains a long guidance bundle
    When Pi renders the collapsed tool result
    Then one compact lifecycle result row is shown
    And the full guidance is not printed into that row
    When the user expands the result
    Then displayed details remain bounded
    And model-facing guidance is not truncated by display limits

  Scenario: Oversized guidance is rejected rather than truncated
    Given the resolved required guidance exceeds 64 KiB
    When that capability is loaded
    Then loading fails without returning a partial bundle

  Scenario: Focused refinement loads its owning concern
    Given the user requests typography, color, layout or product copy refinement
    When typeset, colorize, layout or clarify is loaded respectively
    Then the bundle contains its owning canonical topic and required shared constraints
    And unrelated specialist topics are disclosed rather than included unconditionally

  Scenario: Topic expansion preserves source decisions without duplicate owners
    Given pinned layout, typography, color and writing source sections
    When those topics are synthesized
    Then exact scoped defaults and meaningful exceptions are retained
    And accessibility compliance requirements link to their canonical owner
    And each completed source section maps to an existing destination anchor
    And pending inventory is updated only for coverage actually completed

  Scenario: First-slice provenance preserves inventory and honest coverage
    Given the pinned taste sources contain 65 skill Markdown files including companions
    When first-slice provenance is validated
    Then each inventoried file has a source path and SHA256 fingerprint
    And each completed source-section mapping resolves to an existing canonical destination anchor
    And multiple sources may feed one canonical section
    And one source may feed multiple canonical sections
    And unfinished selected coverage is explicitly pending
    And excluded coverage has a reason
    And first-slice completion is not reported as complete source integration

  Scenario: Build and review share one press-feedback rule
    Given the sources propose conflicting press-scale defaults
    When component guidance is synthesized
    Then one scoped default has one canonical owner
    And provenance records the alternative and resolution rationale

  Scenario: Occasional pointer press has one scoped default
    Given no established product token specifies press feedback
    And the interaction is an occasional pointer or touch action
    When press feedback is implemented
    Then the canonical recipe selects scale 0.96 over 150 milliseconds
    And it records that this is an editorial default rather than measured superiority

  Scenario: Keyboard feedback is immediate
    Given an action is triggered by keyboard
    When interaction feedback is designed
    Then the result and static feedback appear immediately
    And the optional pointer press-scale recipe is not applied

  Scenario: Reduced motion preserves feedback without displacement
    Given the user prefers reduced motion
    When press feedback is designed
    Then feedback remains perceptible without scaling or displacement
    And a persistent static cue communicates the resulting state

  Scenario: Gesture motion and discrete transitions have distinct scopes
    When canonical interruptibility guidance is loaded
    Then discrete state transitions may retarget with CSS transitions
    And direct manipulation guidance preserves current position and velocity
    And controllable keyframe animation is not falsely described as impossible to interrupt

  Scenario: Retargetable motion respects accessibility
    When animate guidance is loaded
    Then it includes canonical interruptibility and reduced-motion constraints
    And it does not include a full upstream skill gateway

  Scenario: Runtime discloses native and heuristic limits
    Given a project declares a native platform
    When context runs
    Then it reports that native supplements are unavailable
    Given a static fixture triggers an upstream style heuristic
    When the detector runs
    Then that heuristic is advisory rather than a competing canonical design floor

  Scenario: Selected runtime source provenance is reproducible
    Given the shipped runtime files and exact upstream revision
    When the runtime provenance is validated
    Then each selected file has an upstream source fingerprint and disposition
    And retained source bytes and required licenses match their recorded fingerprints

  Scenario: Static contrast evidence is scoped
    Given local HTML with explicitly low-contrast text and background colors
    When the static detector runs
    Then a low-contrast finding includes its source and rule identity
    And primary findings indicate triage rather than complete rendered accessibility verification

  Scenario: Missing static parser dependencies fail actionably
    Given the runtime scripts without installed parser dependencies
    When static HTML detection runs
    Then it fails with an install diagnostic rather than reporting degraded success
