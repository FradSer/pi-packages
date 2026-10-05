Feature: Typed and bounded agent management output
  Agent management receipts are data as well as model-facing text.
  They describe observed execution facts, not work acceptance or guessed acknowledgements.
  This contract applies to tool receipts and readbacks, never delivered Session Results.

  Scenario: Every management outcome has native structured content
    Given the six lifecycle actions and returned failures
    When an output builder receives an exact typed outcome and observed state
    Then details and structuredContent carry the same discriminated data
    And the data validates against a flat-root Pi 1.0 outputSchema with action-specific outcome requirements
    And every outcome names the next actor without inventing a process acknowledgement
    And success requires its action's handle or readback and failures require code and message
    And successful receipts retain their existing renderer metadata
    And failures return isError with an error code and bounded diagnostic
    And no acknowledgement or process transition is invented

  Scenario: Preview limits count UTF-8 bytes and lines
    Given multibyte text, quoted values, control sequences and many lines
    When a management receipt or diagnostic exceeds a preview budget
    Then its complete text is at most 16 KiB and 200 lines including the marker
    And its entire structured JSON and details JSON are each at most 32 KiB
    And every shortened field has explicit truncation metadata
    And normalizing a bounded result again preserves the same fields and markers
    And only live-output previews mention complete Session Result delivery
    And a valid Unicode code point is never split
    And provider diagnostics use the existing safe display sanitizer
    And raw roster records and delivered Session Result bytes are unchanged

  Scenario: Inspect preserves exact authority or reports a limit failure
    Given one known live or stopped incarnation with large output or nested metadata
    When that incarnation is projected for inspection
    Then inspect returns one bounded read-only view with explicit preview markers
    And its top-level state is the observed incarnation status and nextActor is caller
    And exact session, name, status, grants, scope and assignment authority are preserved
    But if exact authority cannot fit then an output-limit error identifies omitted fields
    And the limit error retains the observed state and any supplied control outcome
    And no process is started, revived, stopped or acknowledged by the output module

  Scenario: List is a bounded status-summary page
    Given complete session records followed by complete offline definition records
    When the caller requests a list page
    Then the default page limit is 20 and the maximum limit is 50
    And the offset indexes the caller-supplied combined order
    And list omits full live text with an explicit inspect readback notice
    And shortened optional previews include markers and metadata
    And aggregate text and serialized JSON budgets may reduce the returned page size
    And count retains the total session count while total counts all records
    And returned, omitted, before and remaining counts identify pagination precisely
    And nextOffset advances only past records actually returned
    And excluded records are not copied into details or structuredContent
    And following nextOffset visits each record once without repeats or skips

  Scenario: An unrepresentable record cannot disappear during pagination
    Given a record whose mandatory exact metadata cannot fit on an empty page
    When list reaches that record
    Then it returns an explicit output-limit error with its blocked offset
    And it does not skip that record or expose a misleading next page cursor
