@design_contract
Feature: Flat Harness rules with consistent resolution and append-only guidance
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
      When one expanded invocation is processed repeatedly by lifecycle hooks
      Then each rule is attached once for that invocation
      And a subsequent invocation can receive the guidance again
      And each message identifies its invocation scope

    Scenario: Keep the skill scope in retained model-visible guidance
      Given a registered skill rule is delivered for an expanded invocation
      When a later unrelated task retains that guidance in history
      Then the guidance text names the skill task it applies to
      And retaining the message does not make it a project-wide instruction
      And skill and text guidance are both delivered without rewriting the system prompt

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
    Scenario Outline: Match a project name in any supported text source
      Given a text rule matches A项目 or Project A
      And the current conversation contains Project A in "<source>"
      When the next assistant request is prepared
      Then the project's configured status is eligible for tail append
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

  Rule: Guidance preserves the existing request prefix
    Scenario: Append newly matched guidance at the tail
      Given retained conversation H contains a keyword
      When guidance G is first delivered
      Then the model request contains H followed by G
      And subsequent requests retain G at that same position before newer conversation
      And the system prompt remains unchanged by this guidance

    Scenario: Deduplicate unchanged text guidance by current retained state
      Given the current branch retains an active delivery of a rule revision
      When the same rule matches again without changing
      Then no additional copy is appended
      And a session-global already-seen flag is not the authority

    Scenario: Replace guidance through a new tail update
      Given the current branch retains a delivered rule revision
      When the effective instructions change and still apply
      Then one new tail message identifies the replacement revision
      And the earlier message remains at its original position as history

    Scenario: Retire previously delivered guidance
      Given the current branch retains guidance from a rule
      When the rule becomes disabled or is removed without revealing a replacement
      Then one tail notice identifies the prior guidance as retired
      And repeated preparations do not duplicate the notice

    Scenario: Re-enable an already retired revision
      Given a text rule revision was delivered and subsequently retired
      When the same complete revision is enabled again and matches retained text
      Then one new activation message is appended at the tail
      And the older delivery does not suppress that activation

    Scenario: Retire guidance whose winning definition is invalid
      Given the current branch retains guidance from a text rule
      When a same-id winning declaration becomes invalid
      Then one tail notice identifies the earlier guidance as no longer current
      And the rule is shown as invalid
      And repeated preparations do not duplicate the notice

    Scenario: Preserve delivery state when matching is indeterminate
      Given the current branch retains guidance from a valid text rule
      When the next matching pass times out or is cancelled
      Then existing delivery state remains unchanged
      And no unmatched or retirement conclusion is inferred from incomplete evaluation
      And the status reports incomplete evaluation

    Scenario: Refresh a retained delivery after guidance format changes
      Given the current branch retains a pre-scope delivery of an unchanged text rule
      When the scoped guidance format is loaded after reload or resume
      Then one scoped replacement message is appended at the tail
      And the earlier message remains at its original position
      And subsequent starts deduplicate the scoped delivery

    Scenario: Retire an outdated delivery whose original trigger was compacted away
      Given the current branch retains an unscoped text guidance delivery
      And compaction removed every ordinary text segment matching that rule
      When a later unrelated task starts with the scoped delivery format
      Then one retirement notice marks the old guidance as inapplicable
      And no unrelated replacement instructions are injected
      And repeated starts do not duplicate retirement
      And a later matching task receives one scoped activation

    Scenario: Recover after compaction
      Given compaction removed the identifiable guidance message
      And retained ordinary text still matches the rule
      When the next request is prepared
      Then one current guidance message is appended
      And a historical delivery record alone does not suppress it

    Scenario: Restore branch-local delivery state
      Given another branch already received guidance
      When the current branch matches the rule without retaining that delivery
      Then the current branch receives its own tail append

    Scenario: Deliver guidance durably at the next agent start
      Given a keyword is present in the retained conversation, including a prior tool result
      When the next user turn starts and before_agent_start runs
      Then the guidance is appended once as a persistent tail message
      And it is retained on the branch and present in later requests at that same position
      And delivering it does not schedule an extra model response
      # Limitation: a keyword first introduced by a tool result within the SAME run
      # is picked up at the next agent start, not mid-run; mid-run durable delivery
      # is a documented follow-up pending a verified Pi request-preparation seam.

    Scenario: Report incomplete matching
      Given regular-expression evaluation exceeds its enforceable budget
      When Harness reports its result
      Then status identifies incomplete evaluation rather than no match
      And the regex work can be cancelled without hanging the main runtime

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
