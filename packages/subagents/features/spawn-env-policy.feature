Feature: Spawn environment policy withholds secrets from Agent children

  A spawned Agent child receives an explicit non-secret environment instead of
  the leader's complete environment. The policy is defense in depth against
  accidental leakage into a child's process table, crash reports, and its own
  subprocesses. It is not a containment boundary: a child granted bash can still
  read credential files directly, so kernel confinement remains a separate
  layer.

  Rule: The child receives what it needs to run and authenticate

    Scenario: Runtime essentials pass through
      Given a leader environment containing PATH, HOME, and a locale
      When the child environment is resolved
      Then PATH and HOME keep their leader values
      And the locale keeps its leader value

    Scenario: Pi configuration reaches the child
      Given a leader environment that overrides PI_CODING_AGENT_DIR
      When the child environment is resolved
      Then PI_CODING_AGENT_DIR keeps its leader value
      And the child resolves auth.json and models.json from the same config directory

    Scenario: Proxy and SSH agent configuration pass through
      Given a leader environment containing HTTPS_PROXY, NO_PROXY, and SSH_AUTH_SOCK
      When the child environment is resolved
      Then all three keep their leader values

  Rule: Secrets are withheld by default

    Scenario: Unrelated credentials are withheld
      Given a leader environment containing FIGMA_TOKEN, CF_S3_KEY, and NOTE_ENCRYPTION_KEY
      When the child environment is resolved
      Then none of the three names is present in the child environment
      And no withheld value appears anywhere among the child environment values

    Scenario: A credential whose name embeds a private URL is withheld and not echoed
      Given a leader environment containing an npm auth variable whose name embeds a registry URL
      When the child environment is resolved
      Then the variable is absent from the child environment
      And the withheld-name diagnostic does not reproduce the embedded URL

  Rule: Withholding is observable and reversible, never silent

    Scenario: The resolution reports what was withheld without revealing it
      Given a leader environment containing three secret-bearing names and two ordinary names
      When the child environment is resolved
      Then the result reports the total withheld count
      And the result names the withheld secret-bearing variables
      And the result contains no withheld value

    Scenario: An operator opts one variable back in by exact name
      Given a leader environment containing MY_PROVIDER_KEY
      And the allow variable names MY_PROVIDER_KEY
      When the child environment is resolved
      Then MY_PROVIDER_KEY keeps its leader value

    Scenario: A requested name the leader does not have is reported, not invented
      Given the allow variable names a variable absent from the leader environment
      When the child environment is resolved
      Then the child environment has no empty placeholder for it
      And the result reports the name as missing

    Scenario: Opting in a secret-bearing name is allowed but flagged
      Given the allow variable names a secret-bearing variable
      When the child environment is resolved
      Then the variable reaches the child
      And the result flags that an operator overrode a secret-bearing name

    Scenario: The withheld name list is bounded once, at the source
      Given a leader environment exporting forty credential-shaped variables
      When the child environment is resolved
      Then the reported name list holds at most sixteen names
      And the reported credential-shaped count is the true total
      And the diagnostic reports the truncated remainder
      And the console renders the same bounded list rather than applying its own cap

    Scenario: An allowlisted credential-adjacent name is not counted as withheld
      Given a leader environment containing only PATH and SSH_AUTH_SOCK
      When the child environment is resolved
      Then SSH_AUTH_SOCK reaches the child
      And the withheld count is zero

  Rule: Spawner overrides are authoritative

    Scenario: Caller-supplied bindings always win
      Given a spawn that supplies its own worker binding variables
      When the child environment is resolved
      Then every supplied binding keeps its supplied value
      And a supplied name absent from the allowlist still reaches the child

    Scenario: An override cannot be widened by the leader environment
      Given a leader environment and an override for one name
      When the child environment is resolved
      Then the override value replaces the leader value for that name

  Rule: The spawn path hands the policy output to the child process

    A resolved environment that is not the environment the child actually
    receives proves nothing, so the contract is checked from inside a real
    spawned child rather than against the policy's return value alone.

    Scenario: A real spawned child receives the resolved environment
      Given a leader process exporting a credential-shaped sentinel variable
      When a resident child is spawned through the real spawn path
      Then the child's own environment reports neither the sentinel name nor its value
      And the child's own environment reports PATH, HOME, and its spawner-supplied binding
      And the recorded policy names the sentinel as withheld
      And the recorded diagnostic does not contain the sentinel value

    Scenario: Every name the child received is accounted for
      Given a leader process exporting many variables including a credential-shaped sentinel
      When a resident child is spawned through the real spawn path
      Then every name in the child's own environment was allowlisted, supplied by that spawn, or declared runtime-injected
      And strictly fewer leader variables reach the child than the leader exports
      And the recorded withheld count equals that difference exactly
      And the spawner itself never reads the ambient environment directly

    Scenario: A name the platform runtime injects is declared, not tolerated
      Given the platform runtime adds a variable to every spawned child regardless of the supplied environment
      When a resident child is spawned through the real spawn path
      Then that name is matched against a declared runtime-injected set rather than excused as unexpected
      And no runtime-injected name is credential-bearing
      And no runtime-injected value equals a withheld value
      And when the leader also exports that name, it still counts as withheld
      And the withheld count is not reduced by the runtime putting the name back
