Feature: The role a standalone child actually receives

  A child is a separate `pi` process. Its memory is this process's memory, and a
  role registered here is invisible across that boundary: the only channels into a
  child are the text of its kickoff and the tools it was launched with. So on the
  standalone path the role travels in the kickoff, exactly as a coordinator
  composes it, and what cannot be delivered is reported rather than implied.

  A standalone resident accepts subsequent input through agent_input with its exact
  session handle. Its role is pinned at spawn and delivered with the first accepted
  input only; later prompts retain the same child history.

  Rule: The role reaches the child as text, in the turn that starts it

    Scenario: A standalone child's kickoff carries its role and its work
      Given a standalone child started with a role and a prompt
      When the spawn is issued
      Then the kickoff opens with the role body under a role heading
      And the task prompt follows it exactly once
      And the roster's own prompt field is the task prompt alone

    Scenario: A persisted definition's role reaches a standalone child too
      Given a persisted project definition and a start of that name
      When the spawn is issued
      Then the kickoff carries the definition's own role body

  Rule: A role that cannot be delivered is said out loud

    Scenario: An idle standalone resident is told its role has not reached it
      Given a standalone resident started with a role and no prompt
      When the start is reported
      Then the receipt says the role is registered and unread
      And the receipt does not claim the child has standing instructions

    Scenario: A start that applied the caller's own role needs no role line
      Given a standalone child started with a role and a prompt
      When the start is reported
      Then the receipt carries no role line about the role not being applied

    Scenario: A role with a purpose and no instructions is said, not implied
      Given a child started with a description and no role_prompt
      When the kickoff is issued
      Then the role is registered so the name keeps its purpose
      And the start is reported with the description and no standing instructions

  Rule: Intermediate parent messages are an explicit standalone grant

    Scenario: A child can send bounded intermediate progress only when granted
      Given a standalone child whose explicit tool grant includes agent_message
      When the child emits an intermediate message during its active input
      Then the parent receives a separate intermediate notice with trusted session and input attribution
      And the message is bounded per input and does not settle the child result

    Scenario: Missing agent_message grant does not add the capability
      Given a temporary child or saved role whose effective grant omits agent_message
      When the child starts
      Then its capability grant and extension list omit agent_message

    Scenario: Hosted children do not claim standalone parent-message support
      Given a coordinator-owned child whose grant includes agent_message
      When the child starts through the host path
      Then startup refuses honestly because parent messages are standalone-only
