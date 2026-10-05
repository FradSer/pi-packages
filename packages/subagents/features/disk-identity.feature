Feature: Disk-declared durable identities

  A valid agent.md is the only durable identity. Inline roles live in memory.
  Discovery is read-only and never reads or migrates legacy flat definitions.
  VISION.md supersedes the previous memory/worktree opt-in contract.

  Rule: Only canonical declarations are identities

    Scenario: Discover disk scopes in precedence order
      Given user agents/reviewer/agent.md and project .pi/agents/reviewer/agent.md
      And project .pi/agents/reviewer.local/agent.md
      And an inline session role named reviewer
      When reviewer is resolved
      Then the project-local declaration wins over project, user and session
      And the definition contains no memory, worktree or isolation field

    Scenario: Derived homes and legacy flat roles do not declare an identity
      Given a private data home with memory, workspace, projects and state
      And a legacy agents/legacy.md role
      When agents are discovered
      Then neither directory nor flat role becomes a durable identity
      And discovery creates, rewrites and migrates nothing

    Scenario: Invalid names, mismatched names and symlinked declarations are skipped
      Given canonical-looking declarations with missing required frontmatter
      Or a name that differs from its canonical directory
      Or a symlink in the declaration path
      When agents are discovered
      Then none is discoverable
      And project-local directory suffixes are not accepted as identity names

  Rule: The explicit persistence library writes only the canonical shape

    Scenario Outline: Persist an explicitly authorized definition
      Given an AgentDefinitionInput without persistence or isolation parameters
      When persistAgentDefinition is explicitly called with <scope>
      Then it writes <location> with name, description, tools, optional model and verify
      And its body retains the supplied standing instructions
      And no legacy flat file or user promotion is created

      Examples:
        | scope         | location                                |
        | user          | agents/reviewer/agent.md                 |
        | project       | .pi/agents/reviewer/agent.md             |
        | project-local | .pi/agents/reviewer.local/agent.md       |

    Scenario: Session registration never creates durable files
      Given an inline role with deprecated extra properties at the JavaScript seam
      When it is registered and subsequently cleared
      Then only the supported definition fields enter memory
      And no private home or definition is written

    Scenario: A persistence write cannot follow a symlink or inject frontmatter
      Given a symlinked destination or multiline model or tool id
      When persistence is explicitly attempted
      Then it is refused without changing any existing file
