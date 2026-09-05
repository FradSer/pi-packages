@design @unimplemented
Feature: Agent learning abstracts capabilities from project work
  These scenarios describe the redesign, not currently implemented behavior.
  Memory ownership follows the content and applicability of a lesson, not where it was learned.
  Agent Memory stays in the persisted Agent's own folder.
  Project facts, concrete decisions, and history stay in Project Memory.

  Scenario: A reusable method learned in a project can become Agent Memory
    Given a persisted Agent learns a useful method while completing a project Work Item
    When it submits an evidence-backed Memory Proposal describing the reusable method and its applicability
    Then the proposal is eligible for the existing Agent-level review and merge process
    And originating in a project does not by itself disqualify the proposal
    And approval records the abstracted method in the Agent's own memory folder
    And source project facts and raw history are not copied into Agent Memory

  Scenario: A project decision and its general lesson have different owners
    Given a project records a concrete technical decision and the reasons for it
    When an Agent derives a reusable decision criterion from that experience
    Then the concrete decision and its historical record remain in Project Memory
    And the reusable criterion may be proposed separately for Agent Memory
    And neither memory entry replaces the other

  Scenario: Removing project identifiers does not prove a lesson is general
    Given a proposal removes project names but treats a project-specific choice as a universal rule
    When the proposal is reviewed for Agent Memory
    Then anonymization alone does not qualify it as a reusable capability
    And an unsupported generalization is not merged as a global rule
    And a valid abstraction retains its relevant assumptions and limits

  Scenario: Reusing a method does not import the source project's decisions
    Given an Agent has an approved method abstracted from project A
    When the Agent works on project B
    Then it may retrieve the method from Agent Memory
    And it evaluates the method against project B's context
    And project A's facts, decisions, and history are not automatically loaded through the method or its evidence references

  Scenario: Learning in a project does not create memory for a Temporary Agent
    Given a Temporary Agent completes work and identifies a generalizable lesson
    When the result is retained as work evidence before Agent Promotion
    Then no independent Agent Memory folder is created for the Temporary Agent
    And later Promotion and memory approval remain separate decisions
