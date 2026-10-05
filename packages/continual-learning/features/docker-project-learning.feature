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
