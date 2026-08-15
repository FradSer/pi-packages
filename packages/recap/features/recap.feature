Feature: Session Recap

  As a Pi user
  I want a concise recap of what the session is doing
  So that I can quickly reorient when returning to the conversation

  Scenario: Recap is enabled by default
    Given the recap package is installed
    Then the recap setting "recapEnabled" is true
    And the recap setting "autoRecap" is true

  Scenario: Recap shows after a turn
    Given the recap is enabled
    When the user sends a message
    And the agent finishes responding
    Then a recap is generated from the last user and assistant messages
    And the recap is displayed above the editor

  Scenario: Recap is concise
    Given a recap is generated
    Then the recap text is at most 80 characters
    And the recap is a single line
    And the recap starts with a verb in present tense

  Scenario: Toggle recap on/off
    Given the recap is enabled
    When the user runs "/recap off"
    Then the recap setting "recapEnabled" is false
    And the recap widget is removed from the editor

    When the user runs "/recap on"
    Then the recap setting "recapEnabled" is true
    And the recap widget is shown again

  Scenario: Toggle auto-recap
    Given the recap is enabled
    When the user runs "/recap auto"
    Then the recap setting "autoRecap" is toggled

  Scenario: Generate recap manually
    Given the recap is enabled
    When the user runs "/recap now"
    Then a recap is generated immediately from the last exchange

  Scenario: Recap respects language
    Given the conversation is in Chinese
    When a recap is generated
    Then the recap is in Chinese

  Scenario: Recap updates on each turn
    Given the recap is enabled
    And a recap is shown for the previous turn
    When the user sends another message
    And the agent finishes responding
    Then the recap is updated for the new turn

  Scenario: Recap does not block the user
    Given the recap is being generated
    When the user starts typing a new message
    Then the old recap remains visible
    And the user can type without delay