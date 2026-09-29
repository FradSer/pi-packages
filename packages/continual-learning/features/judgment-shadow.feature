Feature: Observe selector decisions with an optional Judgment surface
  Judgment is an opt-in decision surface that observes the Memory Selector's
  routing and selection in shadow mode. The selector still decides, Judgment
  never authors content, and an inactive Judgment is indistinguishable from no
  Judgment at all.

  Scenario: No configuration leaves Judgment inactive
    Given no API key in the environment
    And no API block in the package configuration
    When a settled task starts incremental learning
    Then no Judgment request is made
    And the selector decides exactly as it does today
    And no observation record is written

  Scenario: An environment API key activates Judgment
    Given an API key in the environment
    When a settled task starts incremental learning
    Then Judgment is active for that run

  Scenario: A configured API block activates Judgment
    Given no API key in the environment
    And an API key in the package configuration
    When a settled task starts incremental learning
    Then Judgment is active for that run

  Scenario: The environment key takes precedence over the configured key
    Given an API key in the environment
    And a different API key in the package configuration
    When a Judgment request is authorized
    Then the environment key authorizes it

  Scenario: An unreadable configuration fails closed
    Given a package configuration that cannot be read safely
    When a settled task starts incremental learning
    Then Judgment is inactive
    And the selector decides exactly as it does today
    And the configuration fault is reported as a diagnostic

  Scenario: A configuration without an API key fails closed
    Given a package configuration declaring a model but no API key
    And no API key in the environment
    When a settled task starts incremental learning
    Then Judgment is inactive

  Scenario: An unknown configuration field fails closed
    Given a package configuration carrying an unsupported field
    When the configuration is resolved
    Then Judgment is inactive
    And the configuration fault names the unsupported field

  Scenario: The selector still decides the selection
    Given Judgment is active
    And Judgment and the selector disagree about which Memory entries apply
    When the run completes
    Then the selector's selection is the one that reaches the parent
    And the disagreement is recorded in the observation

  Scenario: Judgment never supplies Memory content
    Given Judgment is active
    When the run completes
    Then no Memory body, Harness rule, or instruction text originates from Judgment

  Scenario: Only a bounded projection is sent
    Given Judgment is active
    When a Judgment request is built
    Then the request carries the code-derived projection
    And raw tool-result content is absent from the request
    And the request stays within the bounded request budget

  Scenario: A projection clips an oversized request in a fixed order
    Given Judgment is active
    And the Task Slice request text exceeds the projection budget
    When a Judgment request is built
    Then the request text is clipped to the budget
    And the Memory index and harness events survive the clipping

  Scenario: Memory entries are identified opaquely
    Given Judgment is active
    And the private Memory root holds many entries
    When a Judgment request is built
    Then each entry carries an opaque identifier
    And no Judgment question names a Memory filename as its answer key

  Scenario: An absent Task Slice request text still yields a valid projection
    Given Judgment is active
    And the Task Slice contains no user request text
    When a Judgment request is built
    Then the projection is still bounded and well formed

  Scenario: An unreachable endpoint does not affect the pipeline
    Given Judgment is active
    And the Judgment endpoint refuses the connection
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: A throttled endpoint does not affect the pipeline
    Given Judgment is active
    And the Judgment endpoint throttles the request
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: A malformed answer does not affect the pipeline
    Given Judgment is active
    And the Judgment endpoint answers without the expected questions
    When the run completes
    Then the observation records the failure
    And the selector decides exactly as it does today

  Scenario: Cancellation propagates to an in-flight Judgment request
    Given Judgment is active
    And a Judgment request is in flight
    When the run is cancelled
    Then the Judgment request is abandoned
    And the cancellation is recorded as a cancelled observation

  Scenario: An observation carries judgments and agreement, not content
    Given Judgment is active
    When the run completes
    Then the observation records the run's context digest
    And the observation records the model version that answered
    And the observation records each Judgment value and its confidence
    And the observation records the selector's own answer
    And the observation records whether the two agreed
    And the observation contains no request text and no tool output

  Scenario: An observation is written outside both Memory roots
    Given Judgment is active
    When an observation is recorded
    Then it is written beneath the private agent directory
    And it is written outside the private Memory root
    And it is outside the project-shared Memory surface
    And a private Memory root still holds only Markdown children

  Scenario: The observation log is capped and rotated
    Given Judgment is active
    And the observation log has reached its cap
    When another observation is recorded
    Then the log stays within its cap
    And the most recent observations are the ones retained

  Scenario: An instruction embedded in the Task Slice is carried as inert data
    Given Judgment is active
    And the Task Slice contains text instructing the reader to select every
    Memory entry and to create a rule that always confirms
    When a Judgment request is built
    Then that text appears only as projection data
    And the projection builder offers no path that promotes it

  Scenario: A Memory description cannot act as an instruction
    Given Judgment is active
    And a Memory description instructs the reader to treat every entry as selected
    When a Judgment request is built
    Then that description is carried as data bounded to its declared length
    And no Memory filename is used as a Judgment answer key

  Scenario: The promotion report reads only the observation log
    Given an observation log containing agreement and containment outcomes
    When the promotion report is generated
    Then it reports the agreement rate and the containment rate
    And it proposes no threshold of its own

  Scenario: The promotion report is explicit about an empty log
    Given no observation log
    When the promotion report is generated
    Then it reports that no measurement exists
    And it proposes no threshold

  # ── Observability ──────────────────────────────────────────────────────

  Scenario: A shadow observation is visible in the transcript
    Given Judgment is active
    When a shadow observation completes
    Then one bounded lifecycle row names the observation
    And the row reports the answering model and whether the two agreed
    And the row carries no request text

  Scenario: An inactive Judgment records no row
    Given Judgment is not configured
    When a settled task completes
    Then no observation row is recorded

  Scenario: The judgment report shows what has been measured
    Given an observation log containing agreement and failure outcomes
    When the user asks for the judgment report
    Then the report shows the observation count and the agreement rate
    And the report shows the answering model
    And the report states that no threshold has been chosen

  Scenario: An unmeasured report is not shown as a zero rate
    Given no observation log
    When the user asks for the judgment report
    Then the report says nothing has been measured
    And no agreement rate is shown

  Scenario: An unconfigured report names what would activate Judgment
    Given no API key is configured
    When the user asks for the judgment report
    Then the report says Judgment is inactive
    And the report names the configuration that would activate it
    And the report proposes no threshold

  # ── Memory proposals ───────────────────────────────────────────────────

  Scenario: A validated Memory plan is judged before it is applied
    Given Judgment is active
    And a validated Memory plan proposes new entries
    When the parent is about to apply that plan
    Then Judgment is asked whether each proposal is durable
    And Judgment is asked how far each proposal generalizes
    And the parent applies the plan exactly as it does today

  Scenario: A proposal judgment carries its own confidence
    Given Judgment is active
    When proposals are judged
    Then the generality answer carries a confidence
    And the duplicate answer carries a confidence
    And the record keeps both rather than only the noul value

  Scenario: A duplicate question can name an existing entry, or none
    Given Judgment is active
    When a proposal is judged against the Memory index
    Then the duplicate question offers every indexed entry
    And the duplicate question offers an explicit no-match option
    And no Memory filename is used as the answer key

  Scenario: A proposal is judged by its content and not promoted by it
    Given Judgment is active
    And a proposal whose content instructs the reader to accept every entry
    When a proposal projection is built
    Then that content is carried as bounded data
    And the projection builder offers no path that promotes it

  Scenario: A plan with no proposals makes no proposal judgment
    Given Judgment is active
    And a validated Memory plan proposes no new entries
    When the parent is about to apply that plan
    Then no proposal request is made
    And the plan is applied exactly as it does today

  # ── Whole-process participation ────────────────────────────────────────

  Scenario: Every learning surface is observed
    Given Judgment is active
    When a run reaches the Memory, Harness, and AGENTS.md phases
    Then the Memory plan's operations on existing entries are judged
    And the Memory plan's new entries are judged
    And the Harness plan's rules are judged
    And the AGENTS.md plan's instructions are judged
    And the parent applies every plan exactly as it does today

  Scenario: Staleness is asked in the parent's own vocabulary
    Given Judgment is active
    And a Memory entry was selected for the run
    When the Memory plan's operations are judged
    Then the staleness question offers keep, contradicted, superseded, and subsumed
    And an answer can be compared with the plan without translation

  Scenario: A Harness rule's selector and strength are asked as closed sets
    Given Judgment is active
    When a Harness rule is judged
    Then the selector question offers skill, bash, and text
    And the strength question offers guidance, confirm, and block
    And both answers carry a confidence

  Scenario: An AGENTS.md instruction is asked whether it is always in effect
    Given Judgment is active
    When an AGENTS.md instruction is judged
    Then a question asks whether it applies to every future task
    And narrower material is not treated as an always-loaded instruction

  Scenario: A surface with nothing to judge costs nothing
    Given Judgment is active
    And a phase produced no operations
    When that surface is observed
    Then no request is made
    And the plan is applied exactly as it does today

  Scenario: Plan content is carried as bounded data
    Given Judgment is active
    And a Harness rule body instructs the reader to remove every other rule
    When the Harness plan projection is built
    Then that body is carried as bounded data
    And the projection builder offers no path that promotes it
