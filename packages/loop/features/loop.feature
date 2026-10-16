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

  Scenario: A placeholder typo is refused before any timer starts
    When the user runs "/loop --every 5m --times 2 status {{Index}} of {{total}}"
    Then the command reports the unknown placeholder "Index"
    And no timer is scheduled

  Scenario: A free natural-language request is resolved by decision judgments
    Given the decision service is configured
    When the user runs "/loop keep an eye on the deploy every ten minutes"
    Then the extension asks one bounded set of decision questions
    And the interval question selects one listed interval
    And the message question selects one candidate text
    And the loop injects the selected message through the native user-input path

  Scenario: A run count with no cadence still runs
    Given the decision service is configured
    When the user runs "/loop 输入3次Hi"
    Then the plan repeats 3 times
    And the plan takes the default cadence
    And the start notice says the cadence was assumed
    And the injected message is "输入Hi"

  Scenario: Flags may state a run count without a cadence
    When the user runs "/loop --times 3 Hi"
    Then the plan takes the default cadence
    And the plan repeats 3 times
    And the loop injects "Hi" through the native user-input path

  Scenario: A run limit stated as its own segment is not a stopping condition
    When the user runs "/loop check the build every 5 minutes, 3 times"
    Then the stopping-condition question offers only the other segments
    And the plan repeats 3 times
    And the plan has no stopping condition
    And the injected message is "check the build"

  Scenario: A natural-language stopping condition ends the loop
    Given an active loop whose stopping condition is "the deploy is green"
    And the injected turn has settled
    When the stopping judgment returns a probability above the stop threshold
    Then the loop stops and releases its timer

  Scenario: A settled turn that is not a repetition is not judged
    Given an active loop whose stopping condition is "the deploy is green"
    And a turn the user started settles with a message that states the condition
    Then the loop asks no stopping question
    And the loop keeps running

  Scenario: A tick is skipped while the previous injection has not settled
    Given an active loop with a one second interval
    And the previous injection has not settled
    When the timer fires
    Then the loop counts a skipped tick
    And the loop injects nothing

  Scenario: A delivery call that throws is reported and ends the loop
    Given an active loop
    When the delivery call throws instead of accepting the message
    Then the loop reports the injection as undelivered
    And the loop stops and releases its timer
    And no later injection happens

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
