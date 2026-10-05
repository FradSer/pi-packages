Feature: Resident activity visibility

  Rule: A living standalone resident remains discoverable after settlement

    Scenario: A settled result leaves an idle child ready for another input
      Given a standalone child whose result has settled in a TUI session
      When the child remains alive and accepts input at its exact session handle
      Then the above-editor activity row stays visible
      And it says Idle and ready for input
      And it uses pi-kit's static pending marker instead of a spinner
      And it does not show stale streamed text, thinking or tool activity

    Scenario: An unconfirmed stop does not pretend the child is ready
      Given an idle standalone child with a stop request that has not closed it
      When the exact child remains alive
      Then its row stays visible as Stopping with a spinner
      And it does not say Idle or ready for input
      When closure is confirmed
      Then its row disappears

    Scenario: An unanswered result has the same resident visibility
      Given a standalone child with an unanswered settled result
      When the child remains alive for a later input
      Then its row stays visible as idle and ready for input

    Scenario: Activity and lifecycle rows preserve ownership boundaries
      Given starting or working standalone children and an idle sibling
      When one child streams and another settles
      Then starting and working children retain real activity and spinner markers
      And the idle sibling remains visible with a static pending marker
      And children disappear only after confirmed closure
      And hosted children do not create a duplicate standalone row
      And print, JSON and RPC sessions mount no activity widget
