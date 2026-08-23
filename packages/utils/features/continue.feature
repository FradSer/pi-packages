Feature: /continue recovery for incomplete and failed turns
  The utils package exposes /continue and continuation keyword input that can
  resume work without adding continuation text to the model context after an
  incomplete turn. Continuation always retries with the current model and
  configuration: a stale failure is never re-classified into a permanent
  refusal, so switching models or fixing configuration takes effect on the
  very next /continue.

  Background:
    Given the pi-utils-fradser package is installed

  Scenario: A transient model API request fails after retries are exhausted
    Given the latest assistant message has stopReason "error"
    And its error says the provider is overloaded or the network timed out
    When the user runs /continue
    Then the last user request is retried silently
    And the request starts from the existing context without a continuation user message

  Scenario: A model API request fails without an error message
    Given the latest assistant message has stopReason "error"
    And it has no error message
    When the user types "继续"
    Then the last user request is retried silently
    And the request starts from the existing context without a continuation user message

  Scenario: A stale failure is retried after the model or configuration changed
    Given the latest assistant message has stopReason "error"
    And its error says provider authentication is unavailable or quota is exhausted
    And the user has since selected another model or fixed the configuration
    When the user runs /continue
    Then the last user request is retried silently on the current model
    And the stale persisted error is not treated as a permanent refusal

  Scenario: Context overflow recovery has already failed
    Given the latest assistant message has stopReason "error"
    And its error says context overflow recovery failed
    When the user runs /continue
    Then the request is retried silently so a larger-context model or a compacted session takes effect

  Scenario: Provider authentication is unavailable
    Given the latest assistant message has stopReason "error"
    And its error says the API key is invalid or unavailable
    When the user runs /continue
    Then the request is retried silently so corrected credentials take effect

  Scenario: Provider quota or billing is exhausted
    Given the latest assistant message has stopReason "error"
    And its error says quota or billing is exhausted
    When the user runs /continue
    Then the request is retried silently so a switched provider takes effect

  Scenario: The provider blocks the response for safety policy
    Given the latest assistant message has stopReason "error"
    And its error says content filtering or safety policy blocked the response
    When the user runs /continue
    Then the request is retried silently

  Scenario: An unclassified provider error fails
    Given the latest assistant message has stopReason "error"
    And its error is not recognized as transient, authentication, quota, context, or safety related
    When the user runs /continue
    Then the request is retried silently

  Scenario: A response is truncated before completion
    Given the latest assistant message has stopReason "length"
    When the user runs /continue
    Then execution resumes silently from the incomplete point
    And the truncated assistant response is omitted from the retried provider context

  Scenario: A tool-call turn was interrupted before tool results were saved
    Given the latest assistant message has stopReason "toolUse"
    And no tool result follows it
    When the user runs /continue
    Then execution resumes silently from the pending tool work
    And the incomplete assistant tool-call message is omitted from the retried provider context

  Scenario: An interrupted turn keeps its saved tool results intact
    Given the latest assistant message has stopReason "toolUse"
    And its tool results were saved before the turn ended
    When the user runs /continue
    Then the assistant tool-call message and its tool results stay together in the retried provider context
    And the provider continues from the saved tool results

  Scenario: Consecutive failed retry attempts are all omitted
    Given the latest assistant messages are several consecutive failures from automatic retries
    When the user runs /continue
    Then every trailing failed assistant message is omitted from the retried provider context
    And no continuation text is sent as a user message

  Scenario: A partial streaming message was persisted unexpectedly
    Given the latest assistant message has stopReason "pending"
    When the user runs /continue
    Then execution resumes silently from the incomplete turn
    And no continuation text is sent as a user message

  Scenario: A tool call was rejected because its arguments were truncated
    Given the latest message is an error tool result
    And its error says the response hit the output token limit
    When the user runs /continue
    Then the incomplete tool call is re-issued silently
    And no continuation text is sent as a user message

  Scenario: A tool result fails
    Given the latest message is an error tool result
    When the user runs /continue
    Then execution resumes silently from the interrupted step
    And the existing tool error remains the only continuation context

  Scenario: A direct continuation marker never becomes model input
    Given the latest assistant message has stopReason "error"
    When the user runs /continue
    Then a hidden continuation marker may trigger the request
    And the marker and failed assistant response are omitted before the provider request
    And no continuation text is sent as a user message

  Scenario: A completed turn continues visibly
    Given the latest assistant message has stopReason "stop"
    When the user runs /continue
    Then a visible continuation user message is sent
    And that message is included in the model context

  Scenario: A session without any previous request refuses safely
    Given the session branch has no previous model request
    When the user runs /continue
    Then the user is told there is nothing to continue
    And no request is sent to the provider

  Scenario: Entries written by another process are inherited before continuing
    Given the session file on disk ends with an entry the active session has never loaded
    When the user runs /continue
    Then the same session file is reloaded before the continuation starts
    And the continuation extends the latest persisted history instead of creating a sibling branch

  Scenario: The user-selected tree node is the continuation starting point
    Given the user navigated the session tree to an earlier node
    And the session file still contains the abandoned failed branch after that node
    And every disk entry is already known by the active session
    When the user runs /continue
    Then the session file is not reloaded
    And the continuation starts from the selected node
    And the abandoned failed branch is not resumed

  Scenario: Continuation keyword input uses the same recovery path while idle
    Given the agent is idle and the latest assistant message has stopReason "error"
    When the user types "continue"
    Then the continuation request runs through the registered continue command
    And a hidden continuation marker may trigger the request without a user message
