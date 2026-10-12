Feature: Intent-based child controls
  The five intent tools are the only child tool surface. A recorded branch that
  named the retired `agent` tool receives this family on its next session start.

  Rule: Startup separates identity from display labels
    Scenario: A label matches a saved identity
      Given a saved reader identity and a temporary startup with label reader
      When agent_start accepts a prompt and temporary instructions
      Then it starts a temporary child without the saved identity or its private data

    Scenario: An explicit identity is missing or conflicts with instructions
      Given a startup with an unknown identity or saved identity plus instructions
      When agent_start validates the request
      Then it refuses before reservation, storage, or process effects

    Scenario: Startup cannot create an idle child through the intent interface
      Given an agent_start request without a prompt
      When agent_start validates the request
      Then it refuses before reservation or process effects

  Rule: A label is one identifier-shaped display name
    Scenario Outline: An authored label becomes one identifier-shaped display name
      Given an agent_start label of "<authored>"
      When the start is accepted
      Then every row shows the child as "<display>"
      And the receipt, the roster and the notice carry "<display>"
      And the authored text still names the temporary role's purpose

      Examples:
        | authored                       | display                        |
        | File Review                    | file-review                    |
        | Task SQL measured optimization | task-sql-measured-optimization |
        | Fix OAuth 2.0!                 | fix-oauth-2-0                  |

    Scenario: A label holding no identifier character keeps the child's own name
      Given an agent_start label with no ASCII letter or digit
      When the start is accepted
      Then the display name is the child's own name
      And every row still names the child once

  Rule: Next input has bounded FIFO sequencing
    Scenario: Two follow-ups arrive while a child works
      Given a prompted child with accepted initial input
      When agent_input reserves two next inputs
      Then neither input changes the active sequence
      And each input starts once after its predecessor settles and its acknowledgement finishes
      And each final result carries its reserved input ID

    Scenario: A caller cancels an acknowledgement wait
      Given an input reserved on an exact incarnation and already dispatched
      When the caller cancels its wait
      Then the receipt reports uncertainty and the original input ID
      And late confirmation controls only that same input and incarnation

    Scenario: Stop ends accepted inputs that never start
      Given a child with queued next inputs
      When agent_stop records its intent or the child exits
      Then no queued input starts
      And each queued input receives one explicit cancelled notice

    Scenario: Capacity or policy refuses input
      Given eight pending inputs or a total pending body budget of 256 KiB
      When another next input exceeds either limit or the host policy refuses reservation
      Then the input is refused without replacement or silent loss

    Scenario: Hosted settlement arrives before startup acknowledgement
      Given a hosted child settles and its terminal report remains unread
      And a next input waits for the positive startup acknowledgement
      When the queue prepares the next dispatch
      Then the host consumes the prior report and rechecks policy before changing active input metadata
      And the prior result keeps its input ID

    Scenario: A negative hosted startup acknowledgement cannot authorize input
      Given a host reserved an incarnation but did not accept its kickoff
      When startup returns a negative or uncertain outcome
      Then the reservation remains closable but next and steer cannot claim accepted kickoff authority

  Rule: Steering never becomes continuation
    Scenario: An idle target receives steer input
      Given an idle child
      When agent_input uses delivery steer
      Then it refuses without starting a new sequence

    Scenario: Steering acknowledgement arrives after the next input starts
      Given input A receives a steer and input B waits behind it
      When A settles and B starts before the steering acknowledgement
      Then the steer receipt still names A's input ID

  Rule: Model tool selection preserves the single family and its exclusions
    Scenario: A fresh session loads the intent family
      Given no recorded selection and no explicit tool exclusion
      When the extension starts
      Then only agent_start, agent_input, agent_stop and agent_list are selected
      And no second child tool family exists to select

    Scenario: A recorded branch naming the retired tool receives the intent family
      Given an active branch whose recorded selection named the retired `agent` tool
      When the branch is restored
      Then the intent family is selected instead
      And no compatibility adapter and no in-transcript notice is added
      And no user data migration runs on discovery or start

    Scenario: An established branch keeps its recorded intent selection
      Given an active branch with a recorded intent family selection
      When the branch is restored
      Then only that intent selection is restored
      And unavailable or excluded tools never become active

  Rule: The startup contract states what a child can be given
    Scenario: An empty identity is a temporary role, not an empty name
      Given a startup that carries an identity field with no value
      When agent_start validates the request
      Then it starts a temporary child rather than a child with an empty name
      And the declared schema accepts that field as it stands

    Scenario: The tools parameter names every grantable id
      Given the agent_start parameter descriptions
      When a caller reads what the tools parameter grants
      Then it names every id a child can be granted
      And it states that a project-extension tool does not reach a child

    Scenario: An empty definition list says where an identity lives
      Given a working directory holding no saved identity
      When agent_list reports a page with no entries
      Then the notice names the project-local identity path
      And it states that a temporary role needs no identity
