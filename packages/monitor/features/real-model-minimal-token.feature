Feature: Explicit low-token real-model Docker smoke for pi-monitor
  Scenario: One native turn per functional path with a disposable hy4-dev provider
    Given a Docker image built from the current monitor, kit and root sources on Pi 1.5.0
    And a disposable Magpie provider exposing hunyuan-eval/hy4-dev with reasoning off
    And no real upstream credential is written into the image or evidence
    When the compact study invokes each registered monitor surface once natively
    Then terminal matching, exit JSON, failure, missing result, timeout and cleanup are proven
    And asynchronous UI delivery, progressive tool disclosure, prompt guidance and shutdown retain their contracts
    And one real parent model turn selects monitor_start through native Pi validation and TUI repaint
    And measured request count and token usage are reported without monitoring-quality claims
