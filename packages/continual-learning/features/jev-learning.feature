Feature: Evidence-bound Jev judgments
  Scenario: Knowledge and constraints can both apply
    Given frozen evidence with a durable fact and a behavioral restriction
    When independent Noul judgments and metadata Scores are certain
    Then both learning directions and only related Memory are selected

  Scenario: Explicit Memory requests survive uncertainty
    Given an explicit /memory request
    When Jev is uncertain or unavailable
    Then Memory processing continues using the existing selector
    And Harness processing remains excluded

  Scenario: Code checks precede semantic checks
    Given a candidate with an invalid structure or an absent evidence quote
    When parent validation runs
    Then no Jev request and no candidate mutation occur

  Scenario Outline: Candidate semantics cannot authorize mutations
    Given a structurally valid grounded candidate
    When Jev reports <finding>
    Then the candidate becomes a proposal without changing existing Memory or Harness
    Examples:
      | finding                 |
      | speculative knowledge   |
      | transient failure       |
      | duplicate Memory        |
      | conflicting Memory      |
      | broader Harness scope   |
      | uncertain answer        |
      | service unavailable     |

  Scenario: Supplementary Memory stays under parent policy
    Given supported supplementary Memory and an existing propose policy
    When Jev approves its semantics
    Then the parent records a proposal and performs no durable mutation

  Scenario: Empty index retains local routing
    Given an empty Memory index and explicit durable evidence
    When incremental selection runs
    Then the parent routes directly without Jev or a selector worker

  Scenario: Unified configuration or environment credentials opt in
    Given neither a Jev section in continual-learning.json nor TYPESAFE_API_KEY
    When learning runs
    Then no Jev request occurs
    When an environment credential is supplied
    Then the default model and semantic scopes can be used
    And explicit Jev disable in unified configuration overrides environment opt-in
    And neither configuration nor credentials grants write permission

  Scenario: Credentials are inspected before JSON encoding
    Given raw multiline credentials or structured sensitive tool fields
    When Jev input is assembled
    Then the parent stops before any external request and records a controlled reason

  Scenario: Semantic review can discover evidence beyond keywords
    Given usable evidence that the keyword screen misses
    And user configuration grants selection scope
    When incremental learning runs
    Then Jev selection reviews the evidence before the parent declares no opportunity

  Scenario: Probability spread within the selected range is not a routing failure
    Given a validated Score distribution with at least 0.9 probability across relevant levels 2 and 3
    When its confidence in one individual level is below 0.8
    Then the Memory is still selected without treating that adjacent-level spread as uncertainty

  Scenario: Semantic candidates separate knowledge from parent-validated bookkeeping
    Given a grounded Memory body with administrative frontmatter or a Harness rule with executable cases
    When Jev checks support
    Then it judges the proposed knowledge or restriction rather than the bookkeeping
    And credentials anywhere in the original candidate still stop transport

  Scenario: Compatible Memory relations share acceptable probability
    Given supported knowledge whose relation is 0.68 supplement and 0.32 unrelated
    When candidate semantic validation runs
    Then compatible probability is accepted without loosening write authorization

  Scenario: A real workflow requires native material evidence
    Given a stored Memory and parent learning receipt
    When fresh-session effects are verified
    Then only a successful paired native read of its canonical file proves body retrieval
    And a filename in a shell comment does not prove retrieval
    And Harness enforcement requires an exact native error bound to its learned rule

  Scenario: Code proves a single-command matcher before asking about authorization
    Given a parent-validated project block rule whose anchored regex matches only one literal command
    When Jev reviews its lasting authorization
    Then code supplies the decoded command and Jev checks that exact unconditional prohibition
    And an approval exception or task-only restriction remains a proposal
    And regex operators, multiple commands and other selector kinds retain full scope review

  Scenario: Semantic feedback shares one bounded repair slot
    Given a code-valid Harness candidate that Jev holds for unsupported or uncertain semantics
    And apply policy and an unused structural repair slot
    When the parent requests a correction against the same frozen evidence
    Then the correction is structurally revalidated and judged by Jev again
    And only an allowed correction can reach parent application
    And no more than two planner children are used in total
    And an empty or invalid correction retains the original proposal
    And unavailable services and cancellation cannot trigger automatic application

  Scenario: Parent describes a narrow command family without inferring authorization
    Given a blocked command-word prefix with ASCII horizontal separators and a word boundary
    When Jev reviews a future project prohibition
    Then parent code describes the matching command words and argument scope
    And Jev must independently authorize the family, duration and explanation
    And an exact-only instruction cannot authorize the argument family
    And vertical whitespace or regex operators retain general scope review

  Scenario: Equivalent metadata formatting does not become a duplicate proposal
    Given a validated rewrite of an existing selected Memory
    And its complete body text is identical and all three metadata lines are equal after outer whitespace trimming
    And its privacy classification is unchanged
    And the rewrite changes content and leaves metadata keys unindented
    When candidate grounding succeeds
    Then the parent-proven formatting correction is not held as duplicate knowledge
    And body changes, metadata value changes and privacy changes retain relationship review
    And unchanged content and newly indented metadata retain relationship review

  Scenario: Complete workflow improvement requires an actual paired effect gain
    Given real native baseline and Jev runs with matching input, worker and mode
    When the complete improvement gate evaluates every recorded effect
    Then both runs must expose the same boolean checks including all core effects
    And the Jev run must contain actual candidate inference telemetry
    And every Jev effect must succeed with no regression and at least one baseline failure improved
    And equal capability, unpaired evidence and candidate-only accuracy cannot prove improvement
    And metadata-only seed repair requires exact complete expected file contents

  Scenario: Semantic Memory correction is bounded by the same repair quota
    Given an incremental candidate with verbatim frozen evidence but unsupported wording
    When its first semantic judgment is uncertain or unsupported and no repair was used
    Then one read-only correction uses the original evidence and selected bodies
    And parent validation and Jev review both run again before application
    And names, intents and privacy classifications are preserved
    And a rejected correction leaves the original proposal intact
    And prior structural repair, unavailable service, duplicate or conflict consume no further correction

  Scenario: Changed evidence and cancellation prevent semantic correction application
    Given a Memory judgment or correction is awaiting completion
    When its frozen snapshot or selected-body dossier changes or the session is cancelled
    Then no candidate Memory is applied
    And invalid evidence is reported as failure rather than an existing proposal

  Scenario: Lasting per-call confirmation retains native approval
    Given an exact command requires explicit approval before each future invocation
    When Jev checks the literal confirmation rule
    Then it distinguishes this requirement from an unconditional ban or a one-time permission
    And executing the command still requires the real native Allow once or Block decision

  Scenario: Project terminology is eligible durable knowledge
    Given a user affirms a public alias relationship and project entrypoint
    When Memory planning reviews the selected learning evidence
    Then the new supported terminology is retained without requiring a remember keyword
    And the candidate does not infer an ongoing maintenance process or verified status

  Scenario: Generated positive fixtures do not authorize broader restrictions
    Given the user prohibits one exact command and the planner adds an argument-bearing positive case
    When the plan needs correction
    Then preserve the authorized rule identity and intent rather than the unsupported positive fixture
    And an argument-bearing invocation becomes a negative case for that exact-only restriction
    And the corrected matcher and evidence repeat parent validation and semantic review

  Scenario: Legal candidate batches exceed one transport request
    Given twelve independently grounded command-family Harness candidates
    When their thirty-six semantic questions are evaluated
    Then bounded requests run in parallel against the same frozen evidence
    And all answers are required before allowing the batch
    And partial failures retain known usage without claiming complete cost

  Scenario: Batch privacy and bounds are checked before transport
    Given a sensitive question or an oversized individual request in a later batch
    When the batch is prepared
    Then no request is sent

  Scenario: Semantic review understands parent-bound private storage
    Given a validated private preference and permission to send synthetic private evidence
    When Jev reviews its candidate knowledge
    Then the candidate meaning identifies private-only storage
    And Jev cannot change that classification or mirror policy

  Scenario: Full repository evidence remains intact
    Given a repository snapshot larger than twenty-four kilobytes with later corrections
    When the snapshot fits the bounded sixty-four-kilobyte request body
    Then Jev receives the full frozen snapshot including corrections
    And the actual request model field is included in the byte bound

  Scenario: Cited new Memory uses local support and complete counterevidence coverage
    Given parent-validated new Memory with exact citations in a frozen snapshot
    And the complete snapshot exceeds a single bounded Jev request
    When semantic validation runs
    Then support is judged against the complete cited entries
    And every frozen entry is reviewed for contradictions, retractions and scope exceptions
    And existing Memory relationships wait for the parent-read complete bodies
    And only support and complete compatible coverage allow the unchanged atomic plan

  Scenario Outline: Unfinished counterevidence review cannot authorize writes
    Given a locally supported new Memory candidate
    When full evidence review encounters <failure>
    Then the plan remains a proposal without any Memory or Harness writes
    And the receipt reports completed coverage and known usage without private text
    Examples:
      | failure                       |
      | later user retraction         |
      | uncited tool contradiction    |
      | uncertain review              |
      | late unavailable service      |
      | unpartitionable large entry   |
      | too many evidence windows     |

  Scenario: Projection never bypasses whole-input privacy or original citation checks
    Given private credentials in an uncited frozen entry or a forged citation
    When cited semantic validation is prepared
    Then no external request occurs
    And no classification or existing Harness is changed

  Scenario: Harness citation support retains every existing authorization dimension
    Given a code-validated Harness plan with exact operation-indexed citations
    When its full snapshot exceeds one Jev request
    Then the parent passes the same validated citations to semantic review
    And local authority, explanation and selector scope checks still run
    And all snapshot entries are reviewed for permission exceptions and scope limits
    And forged event indexes or incomplete operation coverage stop before transport

  Scenario: Twelve cited Harness operations retain legal batching
    Given twelve structurally valid cited command-family restrictions
    When their support questions exceed the per-request limit
    Then all support and complete counterevidence requests are preflighted before transport
    And no more than four requests run concurrently
    And any failed part retains the entire plan as a proposal

  Scenario: Harness explanation keeps the validated project boundary
    Given a lasting project command restriction and an equivalent short explanation
    When Jev judges whether the explanation adds an obligation
    Then the judgment includes the parent-validated current project scope
    And omitted example arguments cannot make a general prohibition global

  Scenario: Complete review preserves citation context and larger whole entries
    Given a valid candidate citing a lasting user fact
    And an unrelated complete tool result exceeds the preferred window size
    When every serialized request remains within the existing wire limit
    Then the larger entry is retained whole in its own review window
    And every review question also sees the original cited support context
    And all original entries must still be reviewed before the plan can apply

  Scenario: Exact quoted Harness explanation requires no paraphrase judgment
    Given the rule message is byte-identical to its validated original user citation
    When the parent-validated Harness candidate is judged
    Then code establishes only explanation wording equality
    And Jev still judges lasting authorization and executable scope
    And complete counterevidence review and all parent permissions remain required
    And a changed message retains its semantic explanation check

  Scenario: Memory counterevidence cannot mistake write bookkeeping for a claim
    Given a parent-validated new Memory with a persistent fact or preference
    And task instructions delegate learning-file writes to the extension
    When Jev checks the complete evidence for contradictory knowledge
    Then the counterevidence question contains only the Memory content
    And the original full candidate still passes privacy and parent permission checks

  Scenario: Equivalent ASCII tab spelling retains proved command-family semantics
    Given a parent-validated command-family matcher using literal tabs in ASCII horizontal classes
    When Jev checks the same matcher as its escaped-tab spelling
    Then both use code-proved command words and semantic authority and argument-scope checks
    And vertical or Unicode whitespace classes and plain end anchors remain unproved
    And approval exceptions and later revocations still hold the complete plan

  Scenario: Proved command families use executable meaning in full counterevidence review
    Given a parent-validated command family with a code-proved ASCII matching language
    When Jev reviews every original entry for authorization exceptions
    Then the counterevidence candidate retains command words, actual block action, matching range and exact explanation
    And administrative operation labels, rule ids and generated fixtures cannot become permission evidence
    And unproved regex candidates retain the complete semantic matching review
    And later approval exceptions, scope corrections and revocations still stop automatic application

  Scenario: Real Docker evidence excludes transport credentials on failures
    Given a timeout, a copied container artifact or bounded Docker stderr includes transport credentials
    When host evidence is exported and reports are merged
    Then credentials are removed before output truncation and durable export
    And copied original bytes without credentials stay unchanged
    And raw artifacts stay in a private temporary directory and symlink artifacts are rejected

  Scenario: A smaller semantic Harness repair retains omitted opportunities
    Given a structurally valid Harness plan with a supported restriction and an uncertain companion
    When the single read-only repair omits the companion and the complete remaining plan passes parent and Jev checks
    Then the remaining plan may apply under the existing policy
    And the omitted operation and exact reindexed evidence remain a pending review proposal
    And a repair cannot introduce a new rule identity or silently return an empty learning result
    And retained original citations may only change their operation index

  Scenario: Fully cited new Memory support judges knowledge without write bookkeeping
    Given parent-validated new Memory with exact frozen citations and separately checked privacy
    When Jev judges whether its knowledge is supported
    Then the support question contains the complete knowledge body without administrative action or filename
    And full original candidates still pass sensitive-material preflight before transport
    And rewrite and deletion preservation checks retain their operation context

  Scenario: Real inference evaluation does not turn service holds into quality evidence
    Given paired candidate results include a timeout or partial usage
    When the real inference report computes quality and completeness
    Then incomplete service results are separate from semantic decisions
    And a complete report requires both arms with actual model and complete usage
    And a returned uncertain semantic judgment remains a measured hold

  Scenario: A command-family scope repair checks quoted shell operators
    Given a new command restriction is held for uncertain matcher scope
    When the single read-only semantic repair is requested
    Then its task requires negative cases for quoted command strings containing operators and arguments
    And only a family prohibition may use the anchored ASCII family matcher
    And an unresolved correction remains a proposal without Harness writes

  Scenario: Durable Harness quality is independent of workflow completion
    Given a completed real task with a persisted Harness restriction
    When the frozen whole configuration is audited against independent harmless command probes
    Then command text printed by echo or quoted printf must not be counted as an invocation
    And absent restrictions retain missed constraints rather than full quality success
    And invalid whole configurations count as incomplete
    And a changed matcher dependency or an unmatched artifact hash stops the audit

  Scenario: Parent rejection is distinguishable from a Jev hold
    Given an original or repaired Harness plan whose executable cases fail
    When parent validation rejects the plan before semantic inference
    Then its receipt explains the controlled validation category and error count
    And no candidate text, rule identity or evidence quote appears in that diagnostic
    And no rejected rule is applied

  Scenario: One semantic repair receives every held candidate location
    Given complete Jev results with failures on multiple candidates
    When the plugin prepares its one bounded semantic repair
    Then the first failure on each candidate is included as controlled metadata
    And the original whole plan remains held until parent validation and semantic recheck pass
    And unavailable or incomplete service results never imply partial write permission
    And the existing repair input and request limits remain unchanged

  Scenario: Git global options are not mistaken for harmless command text
    Given cited evidence prohibits the Git push command family in this project
    When generating or repairing its matcher
    Then same-project Git global options before push remain positive cases
    And echo and quoted printf of those commands remain negative cases
    And exact-only restrictions and existing rules are not broadened
    And bare-command probes alone do not establish whole-family coverage

  Scenario: Native enforcement evidence is independent of a model refusal
    Given a generated Harness and a real-model session that never attempts Bash
    When fixed safe tool requests exercise real Pi in an isolated agent directory
    Then each request is paired with its actual native tool result
    And prohibited Git calls cannot reach the local marker wrapper
    And harmless command text is allowed
    And this fixture-provider evidence is separate from real inference quality
    And no credentials or remote Git writes are involved

  Scenario: Harness support decomposition is a read-only paired experiment
    Given a frozen parent-valid new command rule held by the real support judgment
    When comparing the current question with a message-and-action support question
    Then only the support question changes
    And original scope, counterevidence, evidence bytes and thresholds remain unchanged
    And rewritten or removed rules retain their complete operation context
    And unlabeled real holds are not assumed to be false holds
    And service failures and incomplete usage remain outside semantic accuracy
    And the experiment cannot grant production writes

  Scenario: Research translates only a code-proven finite Git matcher
    Given a fixed bilingual corpus and a matcher equal to the audited finite Git grammar
    When read-only paired inference compares raw syntax with its proven matching description
    Then support and authorization evidence and all decision thresholds remain unchanged
    And unknown regexes retain the original questions
    And no research judgment grants a production write

  Scenario: Proven finite Git syntax does not supply authorization
    Given an exactly recognized finite Git push matcher and parent-validated citations
    When Jev reviews the proposed Harness
    Then support retains the original candidate
    And scope and complete counterevidence review receive its code-proven matching language
    And unknown matchers retain the original path
    And all permission and uncertainty gates still apply

  Scenario: Read-only finite-family research separates authorization judgments
    Given code-proven finite same-project Git push syntax and frozen original citations
    When research compares general scope review with existing command-family judgments
    Then lasting authorization, explanation fidelity and argument-family limits are checked independently
    And complete counterevidence and all confidence thresholds remain mandatory
    And unknown, disabled, confirmation and non-add rules keep the production path
    And the research result cannot write Memory or Harness

  Scenario: Read-only counterevidence decomposition preserves independent authorization
    Given original cited candidates and the complete frozen evidence
    When research asks only about corrections, exceptions and conflicting observations
    Then support and scope questions are unchanged
    And every original evidence window is still reviewed
    And uncertainty, conflict and service failure still hold the complete plan
    And the experiment grants no write permission

  Scenario: Read-only source identity never becomes truth or permission
    Given every original indexed evidence entry including assistant and tool messages
    When research adds identity derived only from structured message roles
    Then all original content, indexes and questions remain unchanged
    And quoted role text cannot become user authority
    And tool observations remain available to check factual conflicts
    And source identity establishes neither truth nor write permission

  Scenario: Read-only Noul counterevidence experiment has explicit contradiction polarity
    Given the original cited candidates and every complete evidence window
    When Noul judges whether a conflict is established
    Then a value at least 0.9 holds the entire plan as conflict
    And only a value at most 0.1 passes that countercheck
    And intermediate values remain proposals
    And independent support, scope, privacy and permission gates still apply

  Scenario: Memory conflict classification concerns only asserted claims
    Given a user states a project fact and a separate behavioral prohibition
    When research checks a Memory containing only that fact
    Then omitting the separate prohibition is not itself a Memory conflict
    And later corrections and factual scope limits still hold the complete plan
    And Harness judgment, original evidence and every other gate are unchanged
  Scenario: Scope expansion is a single bounded proposition in research
    Given a Harness candidate and the complete frozen original authorization
    When the research judge compares its restriction with the original boundary
    Then both the same scope and a narrower scope count as no expansion
    And an uncertain boundary holds the complete plan
    And independent support and counterevidence checks remain mandatory
    And no research judgment authorizes a file write
  Scenario: A Memory index description cannot invent knowledge absent from its body
    Given a candidate whose body is supported but whose indexed description adds an unsupported claim
    When the research semantic gate reviews the candidate
    Then the description and full body are both treated as proposed knowledge
    And the file name and type remain administrative context
    And the whole plan remains proposed until the description is corrected and rechecked
    And privacy and the original frozen evidence are unchanged

  Scenario: Index descriptions receive independent bounded semantic checks
    Given a parent-valid Memory with frozen citations and an index description
    When Jev validates the candidate
    Then the body retains its original support and relationship checks
    And the description receives independent support, relationship and full-evidence checks
    And a duplicate description does not reject a body that adds supported knowledge
    And a duplicate body remains proposed
    And a failed description identifies only its controlled field and candidate index
    And all extra questions fit existing limits before any external request

  Scenario: Research parent-bound matching proof never grants semantic authority
    Given an exact canonical project push matcher and a parent-owned frozen identity
    When the read-only research judge verifies directory, run, scope and evidence digest
    Then code supplies only the matcher meaning to independent authorization judgments
    And wrong bindings retain the general scope judgment
    And temporary, conditional, parameter-limited or revoked restrictions remain proposals
    And the research judge never writes a Memory or Harness

  Scenario: Parent-bound project matcher preserves independent semantic gates
    Given a new blocking rule exactly matches the canonical project push template
    And the parent froze its directory, run, scope and full evidence identity
    When Jev checks that rule during initial validation or bounded repair
    Then matching syntax is supplied as code-verified context
    And Jev independently checks lasting authorization, argument scope and every counter window
    And unavailable or uncertain answers keep the whole plan as a proposal
    And existing rules and explicit Memory handling retain their original contracts

  Scenario: Research description retrieval cue uses proposed body as context only
    Given a parent-validated Memory body and its complete index description
    When the read-only research judge interprets an elliptical retrieval cue
    Then the proposed body provides referent context but cannot supply evidence
    And independent body, description, relationship and complete counter checks remain mandatory
    And original privacy scanning and request limits apply before transport


  Scenario: Research retrieval description judges its actual index role
    Given a Memory body and an index description that may be a retrieval cue
    When the read-only research judge checks independent description support
    Then it judges the cue and every claim against frozen original evidence
    And broader scope, speculation, transient faults and invented claims still hold
    And proposed body context cannot supply evidence or authorize a write
    And whole-body grounding, full counterevidence and original privacy gates remain mandatory


  Scenario: Memory candidate descriptions state scoped evidence-backed knowledge
    Given original frozen evidence and either full or incremental Memory planning
    When the generation model proposes a Memory index description
    Then it includes a concise evidence-backed fact or preference rather than a bare relevance trigger
    And preserves the original target, conditions, duration and permission exceptions
    And the existing independent description and body Jev checks still decide support
    And unclear judgments remain proposals without automatic description rewriting


  Scenario: Native probe with a literal exit-status diagnostic is still observed
    Given the exact project-scoped probe followed by a literal exit-status echo
    When its native Bash tool result is an error with the configured learned block message
    Then the evaluator observes the attempted probe and keeps the no-side-effect check
    And foreign cwd, quoted command text, arbitrary suffixes and successful outputs are rejected
    And historical Docker reports remain unchanged with separate offline revalidation

  Scenario: Service diagnosis retains only a trusted HTTP status
    Given an SDK HTTP failure while selecting or validating frozen evidence
    When a whole request or one required batch fails
    Then the existing fallback or proposal includes the first failed request’s trusted numeric HTTP status when available
    And partial responses never authorize candidate application
    And raw error bodies, headers and messages never enter the receipt

  Scenario: Complete new Memory review is observable without partial write authority
    Given new Memory candidates have frozen original citations and descriptions
    When all original support relationship and counterevidence checks complete
    Then the review binds original evidence existing Memory and candidate digests
    And each candidate reports passed and held expected checks
    And same-batch independence is explicitly not proved
    And a held candidate still holds the entire original plan

  Scenario: Incomplete or changed inputs cannot produce a candidate review
    Given a new Memory plan is being semantically reviewed
    When a response is missing or a source dossier changes during review
    Then no complete candidate review is returned
    And original permission and proposal behavior remain unchanged

  Scenario: Complete counter failures locate original evidence without disclosing it
    Given frozen evidence has multiple original whole-entry windows
    When a complete body or description counter judgment is held
    Then its first failure identifies the zero-based window and inclusive original entry range
    And the receipt and bounded repair hints display only controlled numeric locations
    And no raw evidence or private filename is copied into the diagnostic
    And the entire plan remains proposed with all original checks and permissions

  Scenario: Incomplete review cannot invent a failure location
    Given required counterevidence requests are missing cancelled or inconsistent
    When a whole review cannot return complete semantic judgments
    Then no failure window is inferred from reviewed entries or successful requests
    And existing fallback proposal and Harness behavior remain unchanged

  Scenario: Research temporal context preserves the original complete review
    Given original indexed evidence and fully cited new Memory candidates
    When a read-only study adds cited and window indexes to counter instructions
    Then every original entry candidate criterion and confidence threshold remains
    And support requests and original parent privacy checks remain unchanged
    And no chronology observation grants permission or bypasses a held candidate
    And forced offline answers cannot establish measured learning improvement
