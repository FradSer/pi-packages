Feature: Explicit low-token real-model Docker smoke for pi-matt-pocock
  Scenario: One native turn per functional path with a disposable hy4-dev provider
    Given a Docker image built from the current matt-pocock, kit and root sources
    And a disposable Magpie provider exposing hunyuan-eval/hy4-dev with reasoning off
    And no real upstream credential is written into the image or evidence
    When the compact study invokes each command and gateway mode once natively
    And one real parent model turn selects the gateway in a native PTY
    Then catalog resolution, workflow persistence, transitions, completion and cancellation are proven
    And standalone capability, user capability, reference disclosure and invalid routing retain their contracts
    And one real parent model turn selects the gateway through native Pi tool validation
    And measured request count and token usage are reported without capability-quality claims
