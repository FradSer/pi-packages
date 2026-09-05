@design @unimplemented
Feature: Shared communication across Agent Teams roles
  These scenarios specify the redesign, not behavior implemented by the current package.
  Leader and Worker are coordination roles, not separate communication scopes.
  User and project Definition scopes do not create different messaging tools.

  Scenario: Leader, Worker, and peers use the same communication interface
    Given a leader session and two Agent Work Sessions can address each other
    When the leader contacts a Worker
    And that Worker replies to the leader and contacts its peer
    Then every sender uses agent_event with message, optional to, and optional status
    And no role-specific communication tool or message format is required

  Scenario: A leader can communicate without a Worker assignment
    Given the leader has a trusted Pi session identity and no Assignment Attempt
    When the leader sends an ordinary message to an addressable Work Session
    Then the runtime binds the message to the leader session
    And no Worker assignment or persisted Agent identity is fabricated for the sender
    And sender Work Item and Assignment Attempt bindings are not required for that ordinary message
    And any addressed work context remains distinct from the sender's execution authority

  Scenario: Replies preserve their originating work context
    Given one Agent has concurrent Work Sessions in projects A and B
    And the leader's message addresses the Work Session in project A
    When that Work Session replies using the supplied reply route
    Then the reply reaches the originating leader conversation
    And project B receives neither the message nor the reply

  Scenario: Omitted recipients require one bound reply route
    Given a leader or Worker is sending an ordinary message without to
    When the sender has exactly one applicable bound reply route
    Then the message uses that route
    But when the route is absent or ambiguous
    Then the send is rejected without creating work or waking a recipient
    And the result requests an explicit recipient rather than guessing one

  Scenario: Communication does not itself grant work authority
    Given a leader or Worker can communicate through agent_event
    When the sender requests a state transition
    Then the runtime validates the relevant work binding and transition authority
    And an ordinary message does not complete, reassign, or grant permissions to work
    And receiving a request does not itself authorize an ownership transfer

  Scenario: Directed assignment guidance shares the message delivery protocol
    Given a coordinator addresses existing work through agent
    When that operation produces guidance for the current Work Session
    Then the guidance uses the shared correlated message delivery protocol
    And it does not introduce a leader-only message transport

  Scenario: Progressive tools do not remove shared communication by role
    Given leader and Worker execution capabilities differ
    When the runtime progressively discloses tools and permitted state transitions
    Then ordinary authorized communication remains available through agent_event on both sides
    And advanced transition permissions are checked separately from the ability to send a message
