Feature: Learning on real open-source projects in isolated Docker containers
  Scenario: Real tasks teach reusable knowledge across projects
    Given three pinned public GitHub projects each have an isolated container and empty agent storage
    When real Pi completes a regression task and the parent learns from its user and tool evidence
    Then independent project checks verify the added regression
    And receipts identify actual learning attempts and applied changes
    And personal preferences remain private while safe project facts are mirrored byte-identically
    And a new session uses the learned knowledge with actual tool-read evidence
    And a native blocked Bash attempt has no execution side effect while an unrelated command succeeds

  Scenario: Container experiments do not expose host credentials
    Given a real provider is reached through a bounded experiment proxy
    Then host authentication stays outside the image and project containers
    And the proxy permits only the selected model and inference endpoints
    And failures, retries and missing outputs remain visible in the experiment report

  Scenario: Model retry headers reach the HTTP client without extra retries
    Given the model service returns a valid Retry-After delay or HTTP date
    When the bounded experiment proxy forwards that response
    Then the HTTP client receives the original status and accepted retry delay
    And existing error-body credential redaction remains unchanged
    And the proxy adds no retry or wait and retains the existing request budget
    And absent, malformed, duplicate, credential-bearing or hop-by-hop retry headers are not forwarded
    And Jev keeps its existing independent retry policy

  Scenario: Native Memory source proof binds both existing correction slots
    Given one initial generation is followed by one structural and one semantic correction
    When the semantic correction applies after every existing approval gate
    Then the source proof binds all three distinct generation ledgers to the same actual run
    And each ledger matches its receipt usage and explicit completeness without inventing missing values
    And immutable correction artifacts bind the original rejection, source identity and final plan
    And missing, conflicting, foreign or truncated artifacts keep the proof unavailable
    And original failures and unknown costs remain retained without another model call
