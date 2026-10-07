Feature: Workspace seat billing

  Scenario: An admin upgrades a workspace to Pro and the next invoice is prorated
    Given the workspace "Acme B2B" is on the Business plan with 12 seats
    When the admin upgrades the workspace to the Pro plan
    Then the workspace plan is Pro
    And the billing page shows an amount that covers only the remaining days of the current billing period
    And the payment method on file is charged exactly once
    And no seat is lost
