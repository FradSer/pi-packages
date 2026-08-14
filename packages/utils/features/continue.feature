Feature: /continue recovery for incomplete and failed turns
  The utils package exposes /continue and continuation keyword input that can
  resume work without duplicating prompts after interrupted or failed turns.

  Background:
    Given the @fradser/pi-utils package is installed

  Scenario: A transient model API request fails after retries are exhausted
    Given the latest assistant message has stopReason "error"
    And its error says the provider is overloaded or the network timed out
    When the user runs /continue
    Then the last user request is retried silently
    And the continuation prompt tells the model to inspect the API error and current state

  Scenario: A model API request fails without an error message
    Given the latest assistant message has stopReason "error"
    And it has no error message
    When the user types "继续"
    Then the last user request is retried silently
    And the continuation prompt still identifies the previous model request as failed

  Scenario: Context overflow recovery has already failed
    Given the latest assistant message has stopReason "error"
    And its error says context overflow recovery failed
    When the user runs /continue
    Then the continuation prompt tells the model to reduce context or switch models
    And it does not blindly repeat the same overflowing request

  Scenario: Provider authentication is unavailable
    Given the latest assistant message has stopReason "error"
    And its error says the API key is invalid or unavailable
    When the user runs /continue
    Then the continuation prompt tells the user to fix authentication or switch providers
    And it does not blindly retry the same credential failure

  Scenario: Provider quota or billing is exhausted
    Given the latest assistant message has stopReason "error"
    And its error says quota or billing is exhausted
    When the user runs /continue
    Then the continuation prompt tells the user to resolve billing or quota
    And it does not blindly retry the same account limit

  Scenario: The provider blocks the response for safety policy
    Given the latest assistant message has stopReason "error"
    And its error says content filtering or safety policy blocked the response
    When the user runs /continue
    Then the continuation prompt asks for a safe rephrasing or another model
    And it does not blindly repeat the blocked request

  Scenario: An unclassified provider error fails
    Given the latest assistant message has stopReason "error"
    And its error is not recognized as transient, authentication, quota, context, or safety related
    When the user runs /continue
    Then the user is told to fix the reported problem before retrying
    And the same unknown failure is not retried automatically

  Scenario: A response is truncated before completion
    Given the latest assistant message has stopReason "length"
    When the user runs /continue
    Then execution resumes silently from the incomplete point
    And the continuation prompt warns the model not to repeat completed work

  Scenario: A tool-call turn was interrupted before tool results were saved
    Given the latest assistant message has stopReason "toolUse"
    And no tool result follows it
    When the user runs /continue
    Then execution resumes silently from the pending tool work
    And the continuation prompt tells the model to re-issue only missing tool calls

  Scenario: A partial streaming message was persisted unexpectedly
    Given the latest assistant message has stopReason "pending"
    When the user runs /continue
    Then execution resumes silently from the incomplete turn

  Scenario: A tool call was rejected because its arguments were truncated
    Given the latest message is an error tool result
    And its error says the response hit the output token limit
    When the user runs /continue
    Then the incomplete tool call is re-issued silently

  Scenario: A non-retryable malformed request fails
    Given the latest assistant message has stopReason "error"
    And its error says the request is invalid or the model is unavailable
    When the user runs /continue
    Then the user is told to fix the request or switch models
    And the same invalid request is not retried automatically

  Scenario: A tool result fails
    Given the latest message is an error tool result
    When the user runs /continue
    Then execution resumes silently from the interrupted step

  Scenario: A completed turn continues visibly
    Given the latest assistant message completed normally
    When the user runs /continue
    Then a visible continuation message is sent
