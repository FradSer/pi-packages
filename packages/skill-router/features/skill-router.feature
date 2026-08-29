Feature: External skill collection routing
  pi-skill-router is a pure routing package. It downloads external skill
  collection repositories into a user-level managed directory, materializes
  wrapped gateway and leaf skills, exposes them to Pi through the
  resources_discover event, and adds focused routing suggestions. The package
  itself ships no skill content and no skill collection is an npm package.

  Scenario: Package ships only the routing extension
    Given the skill router package manifest is inspected
    Then its manifest exposes the extension entry point
    And its manifest declares no packaged skills

  Scenario: Adding a GitHub collection materializes sub-skills and gateway
    Given a skill collection repository containing two skills
    When the user adds the repository
    Then the repository is cloned into the router cache directory
    And each selected skill is materialized in the collection skills directory
    And a visible gateway skill is generated for the collection
    And the collection registry records source, gateway, and selection

  Scenario: Sub-skills are not exposed as global slash commands
    Given an installed collection with sub-skills
    When Pi asks extensions for additional resource paths
    Then the router returns only the gateway directory
    And sub-skills are not returned as global skill paths

  Scenario: A collection gateway uses its shared skill namespace
    Given a collection whose skills all begin with "lark-"
    When the user adds the collection
    Then the visible gateway is named "lark"
    And the router does not require a prefix

  Scenario: A remote collection uses its source identity for its internal id
    Given the user adds the repository "larksuite/cli"
    When the router materializes the collection
    Then the internal collection id is "larksuite-cli"
    And the materialized internal files live under that id

  Scenario: Selecting a subset of skills routes only those skills
    Given a skill collection repository containing two skills
    When the user adds the repository selecting only one skill
    Then only that skill is materialized into the exposed collection
    And the registry selection records only that skill

  Scenario: Invalid fixture skills are ignored during discovery
    Given a collection repository containing a SKILL.md with unclosed frontmatter
    When the user adds the repository
    Then the malformed file is not offered as a skill
    And valid skills are still available to install

  Scenario: Nested test fixtures are ignored during discovery
    Given a collection repository containing a SKILL.md below a test directory
    When the user adds the repository
    Then the fixture is not offered as a skill

  Scenario: Adding a collection visibly reports progress
    Given the user starts adding a collection
    When the router clones and scans the repository
    Then Pi displays a loading message until the operation settles

  Scenario: Exposed collections are discovered by Pi
    Given an installed collection with materialized skills
    When Pi asks extensions for additional resource paths
    Then the router returns the exposed collection directory as a skill path

  Scenario: A high-confidence request receives a focused suggestion
    Given an enabled collection in "suggest" mode has a route for "bug"
    When the user asks to diagnose a bug
    Then the router adds guidance for only that collection's resolved leaf skill
    And the guidance names the loaded leaf SKILL.md path to read before acting
    And the original user prompt remains unchanged
    And the router does not inject the leaf skill's full instructions

  Scenario: An ambiguous request remains under the model's control
    Given enabled collections in "suggest" mode
    When no route terms match the user prompt
    Then the router does not add collection guidance

  Scenario: Explicit skill invocations are never rerouted
    Given enabled collections in "suggest" mode
    When the user explicitly invokes a skill command anywhere in the prompt
    Then the router does not add collection guidance
    And it also skips Pi's expanded skill invocation prompt
    And punctuation after the skill command does not change this behavior

  Scenario: Other slash requests remain routable
    Given an enabled collection in "suggest" mode has a route for "bug"
    When the user asks a slash-prefixed non-skill request about a bug
    Then the router may add the matching collection guidance

  Scenario: Disabled collections are neither exposed nor routed
    Given a collection configuration disables a collection
    When Pi asks extensions for additional resource paths
    Then the router does not return that collection's exposed directory
    And the router does not add collection guidance for matching prompts

  Scenario: Updating a collection re-materializes the preserved selection
    Given an installed collection whose upstream gained a new skill
    When the collection is updated
    Then previously selected skills are re-materialized
    And the new upstream skill is not routed until selected

  Scenario: Changing a collection selection is explicit
    Given an installed collection and an upstream skill that is not selected
    When the user selects that skill for routing
    Then the selected skill is materialized into the collection skills directory
    And the registry records the new selection

  Scenario: Removing a collection deletes its exposed skills
    Given an installed collection with materialized skills
    When the collection is removed
    Then its exposed directory is deleted
    And its registry entry is removed

  Scenario: Duplicate upstream skill names fail the materialization
    Given a repository with two skills sharing one upstream name
    When the collection is materialized
    Then the materialization fails with a name collision error
    And no partial exposed directory remains

  Scenario: Invalid registry entries fail closed
    Given a registry containing duplicate collection ids or unknown mode
    When the router loads its configuration
    Then it ignores the invalid collection
    And it does not add collection guidance for that collection

  Scenario: Registry routes cannot escape the collection cache
    Given a registry route whose upstream path contains ".."
    When the router loads its configuration
    Then it ignores the invalid collection

  Scenario: Malicious registry cache keys fail closed
    Given a registry entry whose cache key contains ".."
    When the router loads its configuration
    Then it ignores the invalid collection
    And update refuses to refresh that collection

  Scenario: Malicious Git refs fail closed
    Given a registry entry whose ref starts with a git option
    When the router loads its configuration
    Then it ignores the invalid collection
    And update refuses to refresh that collection

  Scenario: Distinct local repositories never share one cache
    Given two local repositories with the same directory basename
    When both are added as collections
    Then each collection materializes from its own source

  Scenario: Symlinked skill directories are rejected
    Given a repository skill directory that is a symlink to an outside directory
    When the user adds the repository
    Then the install fails without modifying the outside directory

  Scenario: Symlinked managed directories are rejected
    Given the router exposed directory is a symlink to an outside directory
    When the user adds a repository
    Then the install fails without writing outside the router root

  Scenario: A symlinked router root is rejected
    Given the router managed root is a symlink to an outside directory
    When the user adds a repository
    Then the install fails without creating a lock outside the router root

  Scenario: Symlinked cache metadata is rejected
    Given an installed collection whose cache metadata is a symlink
    When the collection is updated or its selection is changed
    Then the operation fails without touching the linked repository

  Scenario: External gitdir metadata is rejected
    Given an installed collection whose cache metadata points to an external gitdir
    When the collection is updated
    Then the operation fails without touching the linked repository

  Scenario: Wrapped leaves do not leak nested skill definitions
    Given a selected skill directory contains another SKILL.md below its root
    When the collection is materialized
    Then the nested skill definition is not discovered as another exposed leaf

  Scenario: A pinned ref survives updates
    Given a collection added with an explicit tag ref
    When the collection is updated
    Then the materialized content still matches the pinned tag

  Scenario: Different refs use independent caches
    Given two collections from one repository use different refs
    When both collections are added
    Then updating one ref does not change the other collection's cache

  Scenario: One source ref cannot be installed twice
    Given a collection source and ref are already installed
    When the same source and ref are added again
    Then the second install fails without corrupting the registry

  Scenario: Updates remap skills that moved directories upstream
    Given an installed collection whose selected skill moved directories upstream
    When the collection is updated
    Then the route path follows the skill's new location

  Scenario: Malformed registry entries fail closed
    Given a registry entry with a non-boolean enabled flag or duplicate id
    When the router loads its configuration
    Then it ignores the invalid collection

  Scenario: Skills with CRLF frontmatter are wrapped correctly
    Given a repository skill whose SKILL.md uses CRLF line endings
    When the collection is materialized
    Then the sub-skill is materialized into the collection skills directory
