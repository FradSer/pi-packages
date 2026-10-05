Feature: Optional lossless encoding reduces repetitive report payloads
  Scenario: Full JSON and captures remain reconstructable
    Given compact is explicitly enabled and a payload contains long repeated strings
    When the monitor reports its terminal result
    Then payload_rle reconstructs the exact original report payload
    And structured data and expanded human details remain unchanged
    And status and integrity diagnostics remain visible outside the encoding

  Scenario: Ordinary reports keep their existing format
    Given compact is absent or encoding does not save enough bytes
    When the monitor reports a small or varied payload
    Then the existing report format is preserved
