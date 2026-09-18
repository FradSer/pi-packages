Feature: Generalize Harness lessons without changing semantic scope
  Scenario: Both authoring surfaces select a supported mechanism after examining evidence
    Given feedback about one project-document mistake
    When direct authoring or the read-only planner translates it
    Then evidence leads to a reusable error class before selecting skill, bash or text
    And incidental document tokens, row numbers and verbatim phrases are not arbitrary rule boundaries
    And identifiers are retained only for explicit resource-specific requirements
    And fixtures cover another same-kind document, a rephrasing and unrelated allowed actions

  Scenario: Registry availability is not authorization to narrow project-wide guidance
    Given a semantic requirement applying to the whole project
    When a registered skill happens to exist
    Then its existence alone does not make the requirement skill-scoped
    And unsupported or ambiguous requirements produce diagnostics and no file writes
    And recommending AGENTS.md or another verification surface never authorizes editing it

  Scenario: Skill guidance uses only exact registered names
    Given a finite registry
    When a flat skill rule is proposed
    Then id remains independent from the exact skill selector and instructions are non-empty
    And unknown skills or legacy target and userMessagePattern fields are rejected
    And reading SKILL.md is not an expanded invocation test
    And automatic additions without a registry fail closed

  Scenario: Scope assessment precedes any creation
    Given an authoritative missing target
    When direct authoring considers a lesson
    Then it reads that exact path and assesses expressibility
    And only a supported complete candidate is written once and read back
    And no preliminary empty file is created
