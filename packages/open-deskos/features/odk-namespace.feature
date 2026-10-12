Feature: Pi uses the ODK technical namespace

  Scenario: A reporting machine uses canonical Link configuration
    Given the operator sets ODK_LINK_ADDRESS and ODK_LINK_TOKEN
    When the package reads its configuration
    Then it uses the configured Link
    And previous environment names do not configure a Link
    And the default desks file uses the odk directory

  Scenario: The Console and Shell share the ODK protocol
    Given a Pi Console and an Open DeskOS Shell
    When the Console signs a control request
    Then both use the odk-control-v2 domain
    And no previous protocol domain is accepted

  Scenario: Console tools have one ODK prefix
    Given a Console with a control credential
    When it registers its tools
    Then each tool uses the odk_ prefix
    And no previous tool name is registered
