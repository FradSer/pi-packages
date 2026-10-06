Feature: A caller can use asynchronous delegation without managing its completion

  Scenario: Starting work acknowledges input rather than returning its answer
    Given a prompt authorized for one temporary child
    When agent_start accepts that input
    Then the receipt names the exact handle including its session prefix
    And it says the complete Session Result arrives asynchronously
    And it directs a dependent caller to end the turn for automatic resumption
    And its guidance excludes polling, sleeps, duplicate starts and file searches to wait
    And every settled child stays IDLE for another next input until agent_stop or parent shutdown
    And only a disk agent.md supplies durable identity and private data

  Scenario Outline: A malformed handle is distinguished from a retired incarnation
    Given a child with an exact session handle
    When the caller invokes <operation> with the session prefix removed
    Then the tool refuses the malformed handle before reaching a process
    And it states the required session:name:incarnation format
    And it does not claim that the child is gone

    Examples:
      | operation  |
      | agent_list |
      | agent_input |
      | agent_stop  |

  Scenario: Listing is read-only and includes offline identities separately
    Given a disk identity with no live child and a stopped child session
    When the caller lists children
    Then the content distinguishes process sessions from offline definitions
    And offline definitions carry no exact live handle
    And no private data is provisioned

  Scenario: A stopped child's result and error remain model-readable
    Given a child that has stopped with preserved output and an error
    When the caller lists the children
    Then the tool content includes a bounded output preview and the error
    And it labels settled output differently from work still streaming
    And the complete delivered answer remains unchanged
