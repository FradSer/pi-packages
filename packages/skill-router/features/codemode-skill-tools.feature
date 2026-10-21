Feature: Leaf skills reached as codemode tools
  pi-skill-router registers one codemode-callable tool per routed leaf skill. When
  codemode is available in the session, the model reaches a leaf skill by
  searching codemode's tools and calling the matched one, which returns that
  skill's instructions and the directory its references and scripts resolve
  against. While codemode is unavailable, the router keeps the routing-suggestion
  fallback, so an installed collection stays usable in any session.

  Scenario: Each routed leaf skill is registered as a codemode tool
    Given an installed collection with two routed skills
    When Pi loads the extension
    Then it registers one tool per routed skill
    And each tool name is the router prefix, the collection, and the skill
    And each tool declares codemode exposure and takes no parameters
    And each tool carries its prompt guidelines

  Scenario: A disabled collection registers no skill tool
    Given an installed collection that is disabled
    When Pi loads the extension
    Then it registers no tool for that collection
    And the extension still registers its routing command

  Scenario: A collection is one search namespace
    Given an installed collection with a capability summary
    When Pi loads the extension
    Then every skill tool of that collection shares one namespace
    And the namespace name is the router prefix and the collection
    And the namespace keeps the collection id as an alias
    And the namespace description is the collection capability summary
    And the namespace instructions are the gateway body

  Scenario: A skill tool is searchable by its summary and its upstream description
    Given a routed skill with a workflow summary and a trigger-oriented upstream description
    When Pi loads the extension
    Then the tool description starts with the workflow summary
    And the tool description also carries the upstream description
    And the tool description carries no file path and no installation detail

  Scenario: The searchable text never repeats the upstream description
    Given a routed skill whose upstream description starts with its workflow summary
    When Pi loads the extension
    Then the tool description carries that description once

  Scenario: Calling a skill tool returns instructions and the skill directory
    Given an installed collection with a routed skill
    When the skill tool is called
    Then the call succeeds
    And the result carries the skill's wrapped instructions
    And the result carries the directory that resolves the skill's references and scripts
    And the structured result names the collection, the skill, and the tool
    And the structured result reports an untruncated body

  Scenario: An oversized skill body is truncated with a pointer to its file
    Given a routed skill whose instructions exceed the returned body bound
    When the skill tool is called
    Then the result reports a truncated body
    And the result names the file that holds the complete instructions

  Scenario: A skill tool refuses content outside the exposed tree
    Given a routed skill whose exposed instructions are a symlink to an outside file
    When the skill tool is called
    Then the call is refused
    And the linked content is not returned

  Scenario: A symlinked exposed directory refuses the call
    Given an installed collection whose exposed directory is replaced by a symlink to an outside tree
    When the skill tool is called
    Then the call is refused
    And the linked content is not returned

  Scenario: A deleted clone degrades to the workflow summary
    Given an installed collection whose cached clone is deleted
    When the extension loads
    Then the skill tool description carries only the workflow summary
    And the call still returns the materialized instructions

  Scenario: A body cut at the bound never splits a surrogate pair
    Given a routed skill whose instructions cross the returned body bound at a surrogate pair
    When the skill tool is called
    Then the result reports a truncated body
    And the returned body carries no half pair

  Scenario: A removed collection cannot still serve a skill
    Given a skill tool registered for a collection that is later removed
    When the skill tool is called
    Then the call is refused
    And the refusal names the collection

  Scenario: Codemode availability selects the tools channel
    Given an installed collection with a routed skill
    And codemode is active and declares that it reaches other tools
    When the user asks a request that matches a routing term
    Then the router adds no routing suggestion
    And the leaf skill stays reachable through its skill tool

  Scenario: An allowlist that hides the skill tools keeps the fallback
    Given an installed collection with a routed skill
    And codemode is active and declares that it reaches other tools
    And the session's tool allowlist removed the skill tools from the registry
    When the user asks a request that matches a routing term
    Then the router adds the routing suggestion naming the leaf instruction file
    Because a codemode call could not reach the hidden skill tool

  Scenario: A partially hidden tool set offers the fallback for the hidden skill
    Given an installed collection with two routed skills
    And codemode is active and declares that it reaches other tools
    And the session's tool allowlist kept one routed skill's tool and removed the other
    When the user asks a request that matches the removed skill
    Then the router adds the routing suggestion naming that leaf instruction file

  Scenario: Installing a collection applies its skill tools immediately
    Given the user installs a collection through the router menu
    When the installation flow finishes
    Then the collection's skill tools exist in that same session
    And no reload is needed for them

  Scenario: A refresh updates an existing tool's searchable text
    Given an installed collection whose skill tools are registered
    When the collection's capability summary is edited while the session is live
    Then the existing skill tools carry the new namespace description and gateway instructions

  Scenario: Removing a collection withdraws its skill tools
    Given an installed collection whose skill tools are registered
    When the collection is removed while the session is live
    Then its skill tools are withdrawn
    And the routing command still exists

  Scenario: Disabling a collection withdraws its skill tools
    Given an installed collection whose skill tools are registered
    When the collection is disabled while the session is live
    Then its skill tools are withdrawn

  Scenario: A collection added after the extension loaded keeps the fallback
    Given an installed collection whose skill tools are registered
    And another collection is added after the extension loaded
    When the user asks a request that matches the new collection's skill
    Then the router adds the routing suggestion naming that leaf instruction file
    Because the new collection's skill tools do not exist before the next reload

  Scenario: A codemode that reaches nothing keeps the fallback
    Given an installed collection with a routed skill
    And codemode is active and declares that it reaches other tools but names none
    When the user asks a request that matches a routing term
    Then the router adds the routing suggestion naming the leaf instruction file

  Scenario: A codemode that fails to answer keeps the fallback
    Given an installed collection with a routed skill
    And codemode is active but fails when asked what it reaches
    When the user asks a request that matches a routing term
    Then the router adds the routing suggestion naming the leaf instruction file

  Scenario: A registered but inactive codemode keeps the fallback
    Given an installed collection with a routed skill
    And codemode is registered but not active
    When the user asks a request that matches a routing term
    Then the router adds the routing suggestion naming the leaf instruction file

  Scenario: A session without codemode keeps the fallback
    Given an installed collection with a routed skill
    And codemode is neither registered nor active
    When the user asks a request that matches a routing term
    Then the router adds the routing suggestion naming the leaf instruction file

  Scenario: The gateway names each workflow's skill tool
    Given an installed collection with a routed skill
    When the collection is materialized
    Then each workflow line names the workflow summary, the skill tool, and the relative leaf path