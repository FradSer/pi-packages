Feature: Intent tool lifecycle rows keep controls readable

  The five intent tools expose exact session handles to the model while the
  transcript gives people one collapsed row that names the child once.

  Rule: One result paints one collapsed row

    Scenario: A single-child row reads label, name and status
      Given a child with label reviewer, name review-child and observed state working
      When its agent_input result renders collapsed
      Then the row reads as tool, label, @name and status in that order
      And the child name appears exactly once

    Scenario: The label already carrying the state word is not repeated
      Given a child whose label is the same word as its observed state
      When its row renders collapsed
      Then the state word appears once
      And the row does not print the label and the state as two separate words

    Scenario: The authored prompt or steer headline stays on the row
      Given an authored kickoff prompt or steer headline
      When its row renders collapsed
      Then the headline is on the row, because it is the work itself

    Scenario: Everything else waits for expansion and prints one fact once
      Given an exact session, an input identifier, observed state, pending intent and next actor
      When the row renders expanded
      Then each of those facts appears once
      And no detail line repeats a fact the detail list already carries

  Rule: Every intent operation has a readable subject

    Scenario: Input and stop use the retained child label or name
      Given an exact child session with label reviewer and name review-child
      When agent_input and agent_stop results are rendered
      Then their collapsed subjects use reviewer
      And neither collapsed row contains the exact session handle

    Scenario: An unanswered execution keeps its diagnostic and preview boundary
      Given a retained child whose last execution has no usable final answer
      When its inspection or list row is expanded
      Then its unanswered explanation and provider diagnostic remain visible
      And any preview omission notice remains visible

    Scenario: A roster row names no child and counts only what it hides
      Given a page of retained children with different statuses
      When the agent_list result renders collapsed
      Then the row reads as agent and listed
      And it names no individual child
      And it carries no count, because a page that shows everything has nothing to add
      And an empty page does not claim there are no children

    Scenario: Listing one page does not imply a complete or empty roster
      Given more retained children than fit in one list page
      When one page is rendered
      Then the collapsed row reads as agent, listed and the shown count of the total
      And that count appears only because entries were omitted
      And expansion reveals the remaining count and next offset

    Scenario: A previous operation keeps its display name after replacement
      Given an operation result for a child with a display label
      When the roster no longer contains that exact incarnation
      Then repainting the old row preserves its original display label
      And it cannot adopt a successor's label

    Scenario: A rejected or cancelled input keeps its original child name
      Given an exact child with a display label whose input is rejected or cancelled
      When the child is later replaced or removed from the roster
      Then the failure row preserves the original display label
      And an asynchronous rejection cannot adopt a successor's label

  Rule: Authored control input appears once at the right detail level

    Scenario: Queued and steered input previews remain compact and expandable
      Given a multiline authored input on an exact child
      When its queued or steered result is rendered collapsed and expanded
      Then collapsed mode shows one fitted preview without the exact handle
      And expanded mode shows the authored input once with exact control metadata
      And rendering does not mutate the structured receipt

    Scenario: An authored input includes an exact handle
      Given input text that names an exact child session
      When the row is collapsed
      Then the preview refers to the exact child without displaying its handle
      When the row is expanded
      Then the original input including its handle appears once

    Scenario: Offline role facts remain available
      Given a saved role with scope, source, instructions and tool configuration
      When its list row is expanded
      Then the bounded role description, source, scope, tools and model remain visible

  Rule: Stop and failure rows report process state honestly

    Scenario: Stopping a child does not imply task completion
      Given a confirmed stop result for a child
      When the result is rendered
      Then the summary says the process stopped
      And completion is described as belonging to the child result or task record

    Scenario: An uncertain or rejected control is readable without leaking a handle
      Given an error result with an exact session handle and a diagnostic
      When the result is rendered collapsed
      Then it uses a readable child subject or generic child subject
      And the exact handle is available only in expanded details
      And native error rendering preserves the disposition and readable child name
