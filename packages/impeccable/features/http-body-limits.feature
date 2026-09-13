Feature: Bounded live HTTP requests
  Scenario Outline: Reject oversized live JSON before parsing or applying it
    Given the live server accepts a POST to <route>
    When the request body exceeds 1 MiB even without Content-Length
    Then the server returns HTTP 413 with a diagnostic error
    And it does not parse or apply the body
    And it remains available for subsequent requests

    Examples:
      | route                        |
      | /events                      |
      | /poll                        |
      | /manual-edit-stash            |
      | /manual-edit-repair-decision  |

  Scenario: Decode UTF-8 only after collecting a bounded body
    Given a valid JSON body has a multibyte character split across chunks
    When the request is read
    Then the JSON text preserves that character

  Scenario: A client disconnects during upload
    Given a partial live JSON request
    When the client disconnects
    Then no event is applied and the buffered request is released

  Scenario: A body is exactly at the limit
    Given a live request body is exactly 1 MiB in UTF-8 bytes
    When the complete request arrives
    Then the body is delivered unchanged
