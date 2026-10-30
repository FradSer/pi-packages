@design_contract
Feature: Flat Harness rules with consistent resolution and scoped structured guidance
  These scenarios define the flat-rule runtime and its verification contract.
  Known runtime limitations remain documented separately from tested behavior.

  Rule: Every rule has one identity and one execution selector
    Scenario Outline: Accept a complete rule for an established selector
      Given a rule has a unique id and the selector "<selector>"
      And its payload is "<payload>"
      When its configuration is validated
      Then the rule is valid
      Examples:
        | selector | payload                             |
        | skill    | nonempty instructions               |
        | text     | nonempty instructions               |
        | bash     | nonempty message with no action     |
        | bash     | nonempty message and confirm action |
        | bash     | nonempty message and block action   |

    Scenario: Use omission as the only empty action representation
      Given a Bash rule contains an empty string or null action
      When its configuration is validated
      Then the diagnostic recommends omitting action for pass with message

    Scenario: Validate selectors independently from identity
      Given two rules with different ids target the same registered skill
      When the skill is expanded
      Then both rules contribute their instructions

    Scenario: Keep configuration forms unambiguous
      Given a rule contains more than one selector or an action on a guidance rule
      When its configuration is validated
      Then a diagnostic identifies the incompatible fields

  Rule: All selectors share whole-rule nearest-layer precedence
    Scenario Outline: Resolve the nearest declaration of one identity
      Given a global rule "example" is enabled
      When the project declaration is "<declaration>"
      Then the effective result is "<result>"
      Examples:
        | declaration                | result                                      |
        | absent                     | inherit the global rule                     |
        | a complete rule            | use only the project definition             |
        | id and enabled false       | disable example                             |
        | an empty rules array       | inherit the global rule                     |
        | invalid with id example    | mark example invalid and explain its source |

    Scenario: Re-enable an identity disabled by an outer layer
      Given a global declaration disables "example"
      When the project provides a complete enabled definition of "example"
      Then the project definition is active

    Scenario: Omitted action does not inherit a stronger outer action
      Given a global Bash rule has action block
      When a complete project rule with the same id omits action
      Then the project rule passes matching calls and supplies its message

    Scenario: Change a selector with a complete explicit replacement
      Given an outer skill rule and an inner text rule have the same id
      When the configuration is resolved
      Then only the inner text rule is effective
      And the authoring preview identifies the selector change

    Scenario: Remove a local override
      Given a personal definition overrides a project rule
      When the personal definition is deleted
      Then the project definition becomes effective

    Scenario: Preserve the configured order of every Harness layer
      Given global shared, project-scoped personal, project shared, and project personal layers exist
      When a write or consolidation validates the effective configuration
      Then the layers are resolved in that same nearest-layer order
      And project-scoped personal rules are not treated as global rules

    Scenario: Diagnose duplicate identities
      Given one file declares the same id twice
      When the file is loaded
      Then the entire ambiguous layer has a configuration diagnostic
      And no declaration is chosen by array position
      And without a previous unambiguous snapshot that layer is unavailable and Bash evaluation is incomplete

    Scenario: Report configuration failure honestly
      Given a layer was previously valid
      When that file becomes unreadable or contains malformed JSON
      Then the last valid snapshot is labeled stale with its diagnostic
      And status distinguishes the current file from the snapshot in use

    Scenario Outline: Treat an invalid winning Bash rule as incomplete evaluation
      Given a global Bash block rule has id "example"
      And the project has an invalid Bash declaration with id "example"
      And the project declaration is encountered during "<load>"
      When a Bash call is evaluated
      Then the call waits for configuration repair without executing
      And the outer rule and a previous same-id definition are not substituted
      Examples:
        | load       |
        | first load |
        | hot reload |

    Scenario: Mark incomplete Bash provenance as unknown
      Given Bash evaluation is incomplete before a rule source can be identified
      When a Bash call is held fail-closed
      Then the diagnostic source is unknown
      And the diagnostic file is unknown rather than built-in

    Scenario: Keep a clearly scoped text error separate from Bash
      Given a winning rule has only a text selector with an invalid regex
      And Bash coverage is otherwise complete
      When an unmatched Bash call is evaluated
      Then the call executes normally
      And the text rule diagnostic remains visible

    Scenario: Treat an unclassifiable winning rule conservatively
      Given a winning rule has an id but no valid single selector and is not a disabled declaration
      When a Bash call is evaluated
      Then the call waits for configuration repair without executing
      And unrelated diagnostic tools remain available

    Scenario: Choose the shared project target by default
      Given a rule creation request has no location selection
      When the authoring target is selected
      Then it is the project .pi/harness.json
      And explicit personal selection chooses project .pi/harness.local.json
      And explicit global selection chooses the agent directory harness.json

  Rule: Every matched Bash rule supplies a model-visible message
    Scenario Outline: Produce one decision for a Bash call
      Given matching rule actions are "<actions>"
      When the Bash call is evaluated
      Then its decision is "<decision>"
      Examples:
        | actions                | decision               |
        | no matches             | execute normally       |
        | omitted                | execute with message   |
        | omitted and omitted    | execute with messages  |
        | omitted and confirm    | request one approval   |
        | confirm and confirm    | request one approval   |
        | omitted and block      | leave call unexecuted  |
        | confirm and block      | leave call unexecuted  |
        | block and block        | leave call unexecuted  |

    Scenario: Decisions do not depend on rule ordering
      Given several matching rules include a block
      When the rules are evaluated in every ordering
      Then the call remains unexecuted in every ordering
      And messages from all matching rules are supplied

    Scenario: Append guidance without replacing native results
      Given a matching Bash rule omits action
      When the command returns a result
      Then the model receives the rule id and message with the real result
      And native error state, output content, and execution details are preserved
      And the message does not retroactively change the executed command

    Scenario: Bind confirmation to one invocation
      Given one call requires confirmation for several matching reasons
      When the user approves its displayed command and execution parameters
      Then that exact invocation can execute once
      And its model-visible result includes approval and all matched messages
      And another invocation requires evaluation again

    Scenario Outline: Complete a confirmation without execution
      Given a Bash call requires confirmation
      When the confirmation outcome is "<outcome>"
      Then the call remains unexecuted
      And the model receives the outcome and matched messages
      Examples:
        | outcome         |
        | declined        |
        | timeout         |
        | UI unavailable  |
        | cancelled       |

    Scenario: Evaluate changed inputs as a new decision
      Given a command was approved
      When its command, execution parameters, or effective rule snapshot changes before execution
      Then the changed invocation receives a fresh evaluation

  Rule: Skill guidance belongs to a real expanded invocation
    Scenario: Supply guidance once per invocation
      Given a registered skill has two effective matching rules
      When one run starts with the actual expanded invocation
      Then each effective rule occurs once in that run's structured section
      And a subsequent invocation can receive the guidance again
      And each message identifies its invocation scope

    Scenario: Keep the skill scope in retained model-visible guidance
      Given a registered skill rule is delivered for an expanded invocation
      When a later unrelated task retains that guidance in history
      Then the guidance text names the skill task it applies to
      And retaining the message does not make it a project-wide instruction
      And skill and text guidance use additive sections without replacing the complete system prompt

    Scenario: Distinguish reading a skill from invoking it
      Given a tool reads a SKILL.md file
      When skill rules are evaluated
      Then no skill invocation is inferred from that read alone

    Scenario: Diagnose an unavailable skill
      Given the nearest skill rule references an unavailable skill
      When rules are resolved
      Then that rule is shown as unavailable
      And its outer same-id declaration stays shadowed

  Rule: Text guidance scans the retained conversation before the next generation
    Scenario: Report the effective text rule owner
      Given a matching text rule comes from the project-scoped personal layer
      When guidance is delivered through before_agent_start
      Then the diagnostic identifies the user.scoped source and its actual file
      And changing only the source layer with the same rule meaning does not refresh guidance

    Scenario: Preserve the last known owner when text guidance retires
      Given delivered text guidance records its source metadata
      When that rule is removed and the next turn retires it
      Then the retirement diagnostic keeps the recorded source and file identity
      And an older session without source metadata reports an unknown source

    Scenario: Hold text guidance when retained context cannot be reconstructed
      Given the session manager fails while rebuilding retained context
      When the next assistant request is prepared
      Then text guidance matching is reported incomplete
      And no text guidance is activated, updated, or retired for that turn

    Scenario Outline: Match a project name in any supported text source
      Given a text rule matches A项目 or Project A
      And the current conversation contains Project A in "<source>"
      When the next assistant request is prepared
      Then the project's scoped status is eligible for the run-start section
      Examples:
        | source                           |
        | the current user message         |
        | an earlier retained user message |
        | assistant text                   |
        | a finalized tool result          |
        | a retained compaction summary    |
        | a model-visible custom message   |
        | a tool-call string argument      |

    Scenario: Inspect complete visible tool text
      Given a finalized tool result contains a matching keyword beyond its first 2000 characters
      And that text remains visible to the model
      When text rules are evaluated
      Then the rule matches that text

    Scenario: Use actual retained content
      Given a keyword exists only in an abandoned branch, discarded history, thinking, image data, metadata, or excluded shell output
      When text rules are evaluated
      Then those sources contribute no match

    Scenario: Keep the text selector in model-visible guidance
      Given a text rule matches retained conversation about Project A
      When its guidance is delivered while the current prompt concerns Project B
      Then its model-visible text identifies the Project A selector and limited subject scope
      And the matching history remains in place without another copy of unchanged guidance

    Scenario: Match individual text segments
      Given one message ends with A项 and a later message starts with 目
      When a text rule searches for A项目
      Then the two messages do not create an artificial combined match

    Scenario: Use one pre-injection snapshot
      Given rule A instructions contain the keyword for rule B
      And ordinary retained conversation matches only rule A
      When the rules are evaluated
      Then only rule A is eligible in that evaluation
      And existing Harness-owned guidance contributes no match

    Scenario: Exclude Harness notes from string tool results
      Given a tool result stores a Harness Bash or configuration note as a string
      And an adapter may flatten native output and the Harness note into one string
      When text rules scan retained model-visible messages
      Then the Harness note does not trigger a text rule
      And ordinary text in the same tool result remains eligible

    Scenario: Preserve explicit user and custom text that resembles a Harness note
      Given user or non-Harness custom text deliberately contains a Harness note marker
      When text rules scan retained model-visible messages
      Then the explicit text remains eligible evidence

  Rule: Guidance composes through complete run-start sections
    Scenario: Preserve other prompt owners
      Given another extension supplies sections, guidelines, context files or a custom prompt
      When Harness prepares applicable skill and text guidance
      Then it contributes one harness_guidance structured section
      And the other owner's contributions remain unchanged
      And no complete system prompt replacement or custom injection message is returned

    Scenario: Deliver unchanged guidance in every applicable run without duplicate rows
      Given the current branch retains an active text delivery revision
      And ordinary retained text still matches that rule
      When successive turns prepare assistant requests
      Then each run receives the complete current scoped section
      And unchanged text delivery appends no duplicate lifecycle or ledger row
      And reload does not depend on a session-global seen set

    Scenario: A delivery ledger alone cannot keep a trigger alive
      Given the current branch retains only a non-context delivery of Project A guidance
      And ordinary retained conversation and the current prompt do not match Project A
      When the next assistant request is prepared
      Then that rule contributes no guidance section
      And retaining the delivery does not expand its subject scope

    Scenario: Preserve an earlier ordinary topic's explicit scope
      Given retained ordinary text still matches Project A
      And the current prompt concerns Project B
      When Harness prepares a text section
      Then Project A guidance includes its exact selector and subject limit
      And its instructions do not become a project-wide condition

    Scenario: Replace the delivered body after a reviewed owned correction
      Given an automatically learned text rule has parent-written ownership provenance
      And a current original user corrects its permanent instructions
      When the exact owned correction passes every original gate and is persisted
      Then the next applicable section contains the corrected body
      And that section does not contain the obsolete body
      And only one changed text delivery row is recorded
      And an unreviewed correction changes no rule bytes

    Scenario: Retire a previously delivered owned definition
      Given the current branch retains an owned text delivery
      When a reviewed permanent retirement is persisted
      Then the next section identifies the prior guidance as retired
      And subsequent starts neither re-inject its body nor duplicate the retirement

    Scenario: Re-enable a retired revision
      Given a rule was delivered and subsequently retired
      When a complete enabled definition matches ordinary retained text again
      Then the next section contains the current scoped activation
      And the older delivery does not suppress it

    Scenario: Preserve scoped guidance during incomplete evaluation
      Given complete scoped text delivery exists on the current branch
      When matching or configuration cannot be fully evaluated
      Then the section preserves complete prior scoped guidance
      And the transcript reports incomplete evaluation
      And no removal is inferred from incomplete matching
      And historical unscoped bodies are not reintroduced

    Scenario: Respect actual branch and compaction contents
      Given compaction or branching changes retained ordinary text
      When the next run rebuilds its text matching snapshot
      Then only retained model-visible text and the current prompt can establish a match
      And abandoned branches, removed text and non-context delivery records cannot establish it
      And a current ordinary match still receives the section after reload

    Scenario: Filter historical injection messages
      Given the branch retains prior harness-guidance or skill-prompt-guidance custom messages
      When the context hook prepares the request
      Then those historical injections are removed from model context
      And unrelated custom messages remain unchanged
      And current guidance is supplied only through the structured section

    Scenario: Defer a new same-run tool keyword until the next agent start
      Given a tool result introduces a matching keyword after the run has started
      When the current run continues without another agent start
      Then no mid-run text delivery is claimed
      When the next user turn starts with that result retained
      Then the current scoped guidance is eligible for its run-start section
      And delivery does not schedule another model response

  Rule: Authoring verifies effective behavior while preserving ownership
    Scenario: Report a saved but shadowed rule
      Given project-personal configuration overrides a proposed project-shared rule
      When the shared rule is saved and verified
      Then the result distinguishes persistence from effective activation

    Scenario: Preserve automatic-edit ownership
      Given a manually authored rule exists in any layer
      When automatic consolidation proposes an overlapping identity
      Then the parent requests an explicit authoring decision instead of replacing it

    Scenario: Preserve the previous format until explicit replacement
      Given an actual user file uses valid policies, disabled names, and skillPrompts
      When the new format is introduced
      Then compatible declarations remain enforced without automatic migration
      And compatibility notices are distinct from configuration errors
      And its bytes remain unchanged during loading
      When removal is explicitly requested
      Then a before-and-after protection-loss preview requires native authorization

  Scenario: Rejected planner output remains diagnosable without admitting it
    Given a bounded Harness worker finishes with an identity mismatch or multiple plans
    When the parent rejects the initial or single repair output
    Then the receipt contains only a parent-controlled extraction category
    And a private artifact binds the original transport hash and immutable run
    And encoded sensitive output is retained only as a hash
    And no rejected plan is accepted or resampled

  Scenario: A current durable correction is reviewed before old learned guidance is delivered
    Given automatic Harness application and semantic review are enabled
    And a project rule still matches its automatic ownership revision
    When the current original user permanently corrects or retires that rule
    Then the parent reviews only that current user entry before task execution
    And only reviewed updates to those exact owned revisions may be applied
    And fresh guidance and execution gates use the persisted corrected revision
    And temporary exceptions, quoted tool instructions and extension continuations grant no correction
    And failed, uncertain or cancelled reviews preserve the original rule and all costs
    And this early review never acknowledges the unfinished task as learned

  Scenario: Ordinary complete JSON writes cannot impersonate learned-rule correction
    Given an existing Harness rule matches its parent-written ownership revision
    When an ordinary task write changes or removes that declaration or its ownership marker
    Then the write is rejected before mutation
    And parent-reviewed correction and explicit previewed Harness authoring remain available
    And unrelated manual additions preserve every exact owned declaration and marker

  Scenario: Correcting a learned selector retains code-proven matching meaning
    Given a current original user correction of an exact owned rule revision
    And replacement and predecessor selectors use the recognized literal prefix grammar
    When normal semantic review judges the complete correction
    Then every support scope and counterevidence question receives both exact matching meanings
    And raw old and new rules correction identity evidence and independent authorization remain unchanged
    And record ids and revision hashes identify records rather than behavioral claims
    And unrecognized selectors receive no invented matching proof
    And corrections cannot enter the new-rule authority shortcut
    And finite historical request bodies remain unchanged
