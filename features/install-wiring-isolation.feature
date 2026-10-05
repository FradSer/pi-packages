Feature: Install wiring is isolated by default and uses Pi's real package loader
  Ordinary repository checks verify a disposable configured install, not the
  user's personal installation. The separate check:install command remains a
  read-only audit of the user's settings and never installs missing packages.

  Scenario: Default checks do not discover personal settings or extensions
    Given a temporary HOME with unrelated personal package declarations
    And an inherited Pi agent directory and provider credentials
    When the ordinary install wiring suite builds its configured install
    Then HOME and PI_CODING_AGENT_DIR point inside a disposable directory
    And settings declare real local workspace package directories
    And unrelated personal extensions and credentials are not loaded
    And the original settings remain byte-identical

  Scenario: The disposable declaration set passes the unchanged installation audit
    Given disposable settings declaring every workspace Pi package
    When the unchanged installation audit reads those explicit settings
    Then no package declaration is missing and no local source is dead
    And no package is installed and no personal settings are changed

  Scenario Outline: Missing declarations and dead paths remain audit failures
    Given disposable settings with <fault>
    When the unchanged installation audit reads those explicit settings
    Then it fails with a <finding> finding without repairing the settings

    Examples:
      | fault                                | finding |
      | a missing workspace declaration      | MISSING |
      | a nonexistent local package source   | DEAD    |

  Scenario: Real Pi loads the installed coordination manifest bundle
    Given disposable settings declaring the agent-teams package directory
    When the real Pi CLI loads packages from those settings
    Then the manifest resolves the agent-teams root extension and bundled entries
    And agent, task, and message are registered exactly once
    And no obsolete coordination tool or unrelated personal extension is registered

  Scenario: Separately declared packages do not duplicate bundled registrations
    Given disposable settings declaring subagents, tasks, and agent-teams directories
    When the real Pi CLI loads packages from those settings
    Then agent, task, and message are registered exactly once
    And their current flat parameter schemas remain unchanged

  Scenario: Packed resources remain installable without a registry request
    Given disposable HOME and package-manager configuration with no user credentials
    When the registry-free pack check inspects the workspace packages
    Then no packed manifest retains a workspace dependency protocol
    And each coordination tarball contains its declared root entry and runtime sources
    And the bundle's dependency extension paths resolve to real package entries

  Scenario: Real installed tools complete an offline smoke run
    Given the real Pi CLI and disposable configured package settings
    And only a local deterministic provider with disposable credentials
    When Pi executes the public task, message, and agent tools
    Then task creation, listing, taking, and completion obey the current flat contract
    And removed verbs and nonexistent message recipients are rejected
    And agent start waits for real RPC readiness and acknowledged input
    And each successful start receipt follows its own child's correlated native acknowledgement
    And the loopback accepted endpoint observes model arrival only after a real HTTP request
    And model arrival never substitutes for native RPC input acceptance
    And both native children close with no persistent role or session data
    And no production service is contacted

  Scenario: Explicit live audit is opt-in and read-only
    Given PI_INSTALL_SETTINGS explicitly names a settings file
    When the install wiring suite checks those declarations
    Then missing declarations and dead local paths are reported without repair
    And ordinary loader and smoke checks still use disposable HOME and agent settings
    And the separately invoked pnpm check:install keeps its user-install audit semantics
