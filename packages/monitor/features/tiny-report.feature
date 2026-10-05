Feature: Compact direct valid-success replies avoid duplicated metadata
  Scenario: Native direct success can retain payload without repeated identity fields
    Given compact is enabled on a direct successful tool reply
    And payload and captures are valid with no integrity warnings
    When terminal content is produced
    Then status, exit code and every payload value remain present
    And native tool-call correlation replaces repeated label, monitor ID and elapsed text
    And full metadata remains in structured results and UI details
  Scenario: Native tool envelope already identifies a tiny successful call
    Given compact is enabled on a direct tool call
    And success has no payload or diagnostic information
    When the terminal reply is returned
    Then its content contains the explicit success status without duplicated label, monitor ID or elapsed time
    And full terminal metadata remains in structured results and human details

  Scenario: Important terminal data and asynchronous identity remain explicit
    Given the result contains payload, errors or truncation or arrives asynchronously
    When it is formatted with compact enabled
    Then metadata and diagnostic fields remain explicit
    And default noncompact output remains compatible

  Scenario: An inactive unused monitor does not add fixed context
    Given monitor_start is inactive and no monitor results exist in live or restored context
    When the agent starts a turn
    Then monitor leaves the system prompt and tool selection unchanged
    And guidance returns when the tool is activated or prior monitor data exists

  Scenario: Real Pi history shapes preserve guidance without activating tools
    Given monitor tools are inactive
    When native session history contains monitor custom messages, tool results or summaries
    Then safety guidance remains present
    And empty history and unrelated custom messages add no monitor guidance
    And active tool selection remains unchanged

  Scenario: Expanded provider measurements verify strict outcomes and complete payloads
    Given repeated and nonperiodic JSON, progress logs and short adversarial commands
    When bare bash, loaded bash, compact exit monitor and inactive bash run each command three times
    Then required JSON values and named captures equal the command oracle
    And failure and missing-result cases do not become pure success
    And native call correlation and lossless encoded payloads remain verifiable

  Scenario: JSONL trace records preserve Unicode separators inside payloads
    Given a native trace contains JSON strings with Unicode line and paragraph separators
    When the measurement reader parses newline-delimited records
    Then only literal newline record boundaries are split
    And each payload remains unchanged

  Scenario: JSON report cleanup preserves valid control-code data safely
    Given a required JSON value contains C1 characters and Unicode separators
    When terminal content is formatted with either compact setting
    Then parsed model-facing JSON equals the original value
    And no raw terminal control codes are emitted

  Scenario: JSON separators require a matching regex contract
    Given JSON contains Unicode line or paragraph separators
    When the caller uses a dot-only JSON capture pattern
    Then completion is result_missing
    When the caller uses an all-character JSON capture pattern
    Then the complete JSON value is captured and returned

  Scenario: Related independent monitor jobs preserve full data in one codemode call
    Given eight independent jobs produce required JSON values
    When one codemode call waits for all terminal contracts
    Then eight complete JSON values are returned in input order
    And parse, truncation or unexpected terminal states retain the full terminal report
    And the comparison includes a grouped bash baseline with scheduling differences disclosed
