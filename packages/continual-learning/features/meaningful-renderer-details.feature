Feature: Harness expansion shows additional information
  Rendering removes only fields already represented by the lifecycle title.
  Policy decisions, check results, guidance delivery and stored entries do not change.

  Scenario: A policy reason appears once while its explanation remains available
    Given a recorded policy match with a reason, policy, action, outcome, tool, source and file
    When its registered entry renderer is expanded
    Then the reason appears once as the title subject without a repeated reason field
    And policy, action, outcome, tool, source and file remain visible
    And action and outcome remain visible even when their words overlap the label

  Scenario: Check titles replace redundant status and detail fields
    Given an output or artifact check with a status, detail, phase, policy and path
    When its registered entry renderer is expanded
    Then the status remains in the check label and the detail appears once as its subject
    And no repeated status or detail field is shown
    And phase, policy and path remain visible when present

  Scenario: Guidance titles replace redundant skill and rule fields
    Given a skill prompt, skill rule or text rule with source, file and prompt text
    When its registered entry renderer is expanded
    Then the skill or rule identity appears in the title rather than a repeated field
    And the row is tagged as Harness guidance, not as another surface
    And source, file and the complete prompt remain visible
    And meaningful prompt text is retained even when it contains the title subject

  Scenario: Guidance recorded under the previous entry type still renders
    Given a retained transcript entry persisted under the earlier guidance entry type
    When its registered entry renderer is expanded
    Then it renders exactly like a current guidance row
    And no stored entry data is rewritten

  Scenario: Narrow rows reveal the complete subject without a duplicate detail
    Given a policy reason, check detail or guidance identity longer than the terminal width
    When its registered entry renderer is collapsed and then expanded
    Then the collapsed row advertises expansion
    And expansion wraps the complete subject without repeating it as a field
    And every rendered line remains within the available width

  Scenario: Full guidance survives both character and detail-line limits
    Given a guidance prompt longer than 2000 characters and 50 lines
    When its registered entry renderer is expanded at wide or narrow terminal widths
    Then every prompt line including the final line remains visible
    And source and file remain visible
    And rendering leaves the stored entry unchanged
