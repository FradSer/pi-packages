Feature: Management tool outputs are typed and bounded independently of final answers

  Rule: Data reaches native and programmatic callers

    Scenario: Every intent operation and returned refusal declares a structured contract
      Given the intent output schema and its lifecycle operations
      When native tools or direct library calls return
      Then content remains readable and details support the existing renderer
      And structuredContent has the same operation, disposition, observed state and next actor
      And schema validation refuses a mismatched operation or disposition, or missing required authority

    Scenario: Failed controls retain honest machine-readable authority
      Given an exact resident whose input is rejected, unacknowledged, or whose startup fails
      When the operation returns a failure
      Then its operation and failure code identify the control
      And known exact handle and observed state remain diagnostic facts
      And rejection is distinct from uncertain or unconfirmed control outcome
      And only genuinely pending work has a pending intent

    Scenario: Coalesced result precedes the acceptance receipt
      Given a child settled its answer synchronously before its startup acknowledgement
      When the start receipt returns
      Then its observed state is IDLE with caller as next actor
      And it claims no pending result while the actual answer was delivered once

  Rule: Budgets apply to a complete management response

    Scenario: One preview obeys Unicode-safe text and JSON budgets
      Given large multibyte output, long diagnostics or many lines on a known roster entry
      When agent_list reads the roster
      Then text is at most 16 KiB UTF-8 and 200 lines
      And each details or structuredContent serialization is at most 32 KiB
      And shortened fields have explicit markers and original/output size metadata
      And raw roster state and complete asynchronous final-answer bytes are unchanged

    Scenario: A list page does not repeat every answer body
      Given many retained live or stopped records and offline definitions
      When agent_list receives offset and limit
      Then it returns status summaries without liveText bodies
      And a page may return fewer entries to obey aggregate budgets
      And it reports complete totals, omissions and nextOffset
      And following cursors on an unchanged roster neither skips nor repeats records

    Scenario: Diagnostics are bounded consistently on inspection and listing
      Given a raw error longer than the diagnostic budget
      When either readback is returned
      Then it is sanitized and shortened to 1000 characters with a diagnostic marker
      And formatting twice does not re-truncate its own marker or duplicate metadata

    Scenario: Truncation metadata never grants budget bypass
      Given caller-supplied preview metadata claiming a larger raw field is already bounded
      When the output builder normalizes that record
      Then it checks actual byte and line limits and strips unsafe diagnostic controls
      And only a marker whose measured output agrees can be reused without duplicate shortening
      And the raw record remains unchanged

    Scenario: Exact authority cannot fit in one readback
      Given an unusually large exact assignment, grant or identifier
      When it cannot be represented within the management budget
      Then output-limit is explicit with preserved representable authority and named omissions
      And it never claims a process or input failed merely because its readback was limited

    Scenario: Budget reduction cannot erase a schema-required input preview
      Given an accepted next or steer delivery with a large exact grant and authored prompt
      When its combined structured receipt exceeds the management budget
      Then the required prompt is retained as a bounded preview or an output-limit is explicit
      And no schema-invalid success is returned by deleting a required field

    Scenario: A failed operation returns a bounded diagnostic
      Given an invalid request or native operation with a large error
      When it returns a refusal
      Then both text and structured failure are bounded and schema-valid
      And operation, failure code, known exact handle and uncertainty remain machine-readable

  Rule: Final results are not management previews

    Scenario: A long final answer returns automatically
      Given a started exact child with a complete answer beyond management budgets
      When its turn settles
      Then the asynchronous Session Result retains all authored bytes
      And only a later agent_list read has management preview limits
