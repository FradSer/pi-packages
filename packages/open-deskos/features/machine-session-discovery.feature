Feature: Discover this machine's existing session metadata without reading histories

  Scenario: One configured reporter discovers sessions across workspaces
    Given directory-sessions metadata contains working, idle, settled, and exited sessions
    And some records claiming to run have dead or invalid process IDs
    When the configured reporter starts and refreshes the metadata inventory
    Then live working sessions are running and live idle sessions are settled
    And dead process records and explicitly exited records are exited
    And session timestamps are the metadata timestamps rather than the scan time
    And timestamp-prefixed UUID aliases describe one session
    And wire inventory records carry discovered provenance so a live direct reporter stays authoritative even when metadata was written later

  Scenario: Discovery reads only bounded metadata
    Given the registry contains partial, malformed, oversized, and linked files
    When discovery scans the registry
    Then valid partial identity and descriptive fields are retained without invented timestamps
    And malformed, oversized, non-regular, and linked files are skipped
    And directory entries, workspace count, file count, and bytes per file are bounded
    And no session histories, credentials, or arbitrary extra metadata are read or reported
    And no registry file is created, changed, or removed

  Scenario: A discovery snapshot never displaces the current session
    Given the reporter has current live identity and bounded events
    And discovery contains a stale alias of that session and more than 64 other sessions
    When the reporter replaces its discovered snapshot
    Then the combined session count is at most 64
    And current live identity, status, start time, and events win over discovered metadata
    And only discovered entries absent from the next snapshot disappear
    And discovery preserves running sessions before settled sessions before exited sessions
    And only the current session is pinned so exited observed history cannot crowd out live discovered work at the cap

  Scenario: Multiple metadata writers and old process sessions remain truthful
    Given two metadata aliases describe the same session with complementary fields
    And several distinct sessions have the same live process ID after a session switch
    When discovery resolves the inventory
    Then aliases merge using the newest metadata state without losing older optional fields
    And only the newest unambiguously identified session of a live process can be running
    And older sessions of that process are exited
    And PID reuse by a non-Pi process or a Pi process started after the metadata never revives the stale session
    And liveness uses one bounded process snapshot rather than one command per PID
    And zombie or dead process-table states never count as running Pi sessions

  Scenario: A formerly observed session is resumed by another Pi process
    Given the reporter switched away from a session and retained its events
    And another live Pi process resumed that session with newer metadata
    When discovery refreshes
    Then the resumed session's metadata may replace its old observed exited state
    And the retained events and the currently active session remain intact
    And when resumed metadata disappears the retained historical session becomes exited without inventing a new activity timestamp

  Scenario: Refresh lifecycle does not leak background work
    Given a configured session has started metadata discovery
    When periodic refresh runs while an earlier scan is still pending
    Then scans do not overlap
    When session shutdown, replacement, or reload stops discovery
    Then pending refresh results are ignored and scheduled refreshes are cancelled
    And stale reconnect callbacks cannot reopen the closed reporter
    When the next session starts
    Then exactly one new refresh loop and one link can start

  Scenario: Full inventories fit the Desk Link frame limit
    Given 55 or 64 sessions with long multi-byte descriptive metadata
    And the reporter owns the current live identity and events
    When the reporter writes a complete sessions snapshot
    Then the newline-delimited record is at most 65536 bytes
    And discovered name, goal, and activity may shorten further without changing IDs or timestamps
    And full working-directory paths and workspace names are preserved as workspace identity
    And the current live identity and events remain intact
    When exact identity fields alone cannot fit the frame budget
    Then the current session remains and lower-priority whole records are omitted
    And the open-deskos command reports the omitted count instead of silently losing the complete inventory

  Scenario: Missing configuration never starts discovery
    Given either Desk Link address or token is absent
    When the extension loads
    Then no discovery timer, metadata scan, or socket is started
