Feature: Cancellable collection lock acquisition
  Scenario: A competing operation releases its lock
    Given another operation owns the collection registry lock
    When a collection change waits for that lock
    Then the event loop remains responsive
    And the change resumes after the owner releases the lock

  Scenario: Cancellation while waiting
    Given another operation owns the collection registry lock
    When the waiting collection change is cancelled
    Then it stops promptly without changing the registry
    And it leaves the other operation's lock intact

  Scenario Outline: Uncertain owner checks preserve the lock
    Given another operation owns the collection registry lock
    And checking its owner returns <error>
    When a collection change waits for that lock
    Then it does not remove the owner's lock
    And the change resumes after the owner releases the lock

    Examples:
      | error    |
      | EPERM    |
      | EUNKNOWN |

  Scenario: Cancellation before starting
    Given a collection change has already been cancelled
    When it is called
    Then it creates no registry directory or lock

  Scenario: Cancelling the loading overlay
    Given the loading overlay is waiting for a collection lock
    When the user presses Escape
    Then the pending lock acquisition is cancelled
    And the overlay closes without applying the change
    And cancellation is shown without an error alert

  Scenario Outline: Cancelling while an external operation is pending
    Given the loading overlay is waiting for <operation> that has not settled
    When the overlay signal is cancelled
    Then the overlay closes promptly without waiting for the operation
    And the collection remains uninstalled
    And a late result cannot complete the overlay again or resume installation

    Examples:
      | operation      |
      | authentication |
      | model response |
