Feature: /loop repeats one message into the session as a real user turn

  Background:
    Given Pi loads the pi-loop extension
    And the extension registers the command "loop"

  Scenario: Explicit flags repeat a message on a fixed schedule
    When the user runs "/loop --every 5m --times 3 check the build"
    Then the loop parses the interval as 300000 milliseconds
    And the loop parses the message as "check the build"
    And the loop injects "check the build" through the native user-input path
    And every injection is an independent user turn
    And no decision request is sent

  Scenario: A template placeholder is expanded for each injection
    When the user runs "/loop --every 1m --times 2 status {{index}} of {{total}}"
    Then the first injected message is "status 1 of 2"
    And the second injected message is "status 2 of 2"

  Scenario: A free natural-language request is resolved by decision judgments
    Given the decision service is configured
    When the user runs "/loop keep an eye on the deploy every ten minutes"
    Then the extension asks one bounded set of decision questions
    And the interval question selects one listed interval
    And the message question selects one candidate text
    And the loop injects the selected message through the native user-input path

  Scenario: A natural-language stopping condition ends the loop
    Given an active loop whose stopping condition is "the deploy is green"
    And the injected turn has settled
    When the stopping judgment returns a probability above the stop threshold
    Then the loop stops and releases its timer

  Scenario: A tick is skipped while the previous injection has not settled
    Given an active loop with a one second interval
    And the previous injection has not settled
    When the timer fires
    Then the loop counts a skipped tick
    And the loop injects nothing

  Scenario: An invalid flag set is refused before any timer starts
    When the user runs "/loop --every 5m"
    Then the command reports that a message is required
    And no timer is scheduled

  Scenario: Semantic mode reports a missing decision credential
    Given no decision credential is configured
    When the user runs "/loop keep an eye on the deploy every ten minutes"
    Then the command reports that semantic mode needs a decision credential
    And no timer is scheduled

  Scenario: Stop releases the active loop
    Given an active loop
    When the user runs "/loop stop"
    Then the loop clears its timer
    And no later injection happens
