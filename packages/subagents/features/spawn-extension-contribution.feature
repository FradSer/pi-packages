Feature: Agent extensions and capability tools are contributed by the caller

  The spawner hardcodes no Agent extension path and no capability tool set. A
  package that installs the execution layer alone therefore grants only pi
  built-ins and never advertises a coordination tool that nothing registers.

  Rule: Each contributing package supplies its own Agent extension

    Scenario: Every supplied extension reaches the child command line
      Given a spawn supplying two Agent extension paths
      When the child process is spawned
      Then the child command line carries both paths, each behind its own --extension
      And --no-extensions is still passed so discovered extensions stay disabled

    Scenario: A bare child holds only pi built-ins
      Given a spawn supplying no Agent extension and no capability tools
      When the child process is spawned
      Then the child command line carries no --extension
      And the --tools allowlist is exactly the role's grant

    Scenario: The public lifecycle explicitly contributes stream classification
      Given a temporary or disk-defined public child
      When the lifecycle selects its child extension paths
      Then it supplies the bounded native stream classifier explicitly
      And that contribution grants no tool or private data
      And the low-level spawner still supplies no ambient extension

  Rule: A declared capability must have something to register it

    Scenario: Capability tools without an extension are refused
      Given a spawn declaring capability tools but supplying no Agent extension
      When the child process is spawned
      Then the spawn fails naming the contradiction
      And no child process is started

    Scenario: A contributed capability set widens the grant and the universe
      Given a role grant of read and a contributed capability set
      When the effective allowlist is resolved
      Then the allowlist is the role grant plus the contributed set, deduplicated
      And a requested id outside pi built-ins and the contributed set is reported unknown
      And with nothing contributed that same id is reported unknown
