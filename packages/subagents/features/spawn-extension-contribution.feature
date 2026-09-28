Feature: Worker extensions and capability tools are contributed by the caller

  The spawner hardcodes no worker extension path and no capability tool set. A
  package that installs the execution layer alone therefore grants only pi
  built-ins and never advertises a coordination tool that nothing registers.

  Rule: Each contributing package supplies its own worker extension

    Scenario: Every supplied extension reaches the child command line
      Given a spawn supplying two worker extension paths
      When the child process is spawned
      Then the child command line carries both paths, each behind its own --extension
      And --no-extensions is still passed so discovered extensions stay disabled

    Scenario: A bare child holds only pi built-ins
      Given a spawn supplying no worker extension and no capability tools
      When the child process is spawned
      Then the child command line carries no --extension
      And the --tools allowlist is exactly the role's grant

  Rule: A declared capability must have something to register it

    Scenario: Capability tools without an extension are refused
      Given a spawn declaring capability tools but supplying no worker extension
      When the child process is spawned
      Then the spawn fails naming the contradiction
      And no child process is started

    Scenario: A contributed capability set widens the grant and the universe
      Given a role grant of read and a contributed capability set
      When the effective allowlist is resolved
      Then the allowlist is the role grant plus the contributed set, deduplicated
      And a requested id outside pi built-ins and the contributed set is reported unknown
      And with nothing contributed that same id is reported unknown
