Feature: Auto-memory injects a bounded, discoverable index

  Project memory keeps per-entry files. The prompt carries relevance metadata,
  not full bodies or per-turn model ranking. Missing metadata is not evidence
  that no relevant memory exists.

  Scenario: The system prompt carries the memory index without entry bodies
    Given memory entries with frontmatter descriptions and multi-paragraph bodies
    When the memories block is formatted for the system prompt
    Then it lists each entry once with filename, source, and description
    And it declares each body root once instead of repeating an absolute read path per entry
    And each entry stays reachable as its declared root joined with the entry filename
    And it contains no entry body text
    And it marks all memory content as untrusted reference data

  Scenario: Declared roots let one budget reach every entry
    Given a corpus whose per-entry read paths repeat long absolute roots
    When the memories block is formatted within its default budget
    Then every entry is listed with filename, source, and a relevance cue
    And no entry is omitted
    And the entry rows and the summary together stay within the budget

  Scenario: An existing long description retains its late relevance trigger when it fits
    Given a description longer than 120 characters whose relevance trigger is at the end
    When the complete description fits in the final index budget
    Then the complete description including its late trigger is injected

  Scenario: A description too large for the budget is visibly shortened
    Given a description larger than the available final index budget
    When its filename, a shortened cue, and the shortened-cue marker fit
    Then the shortened cue is marked rather than presented as complete
    And the block states once that shortened or omitted cues are read from the complete index or the entry file
    And the complete index remains discoverable
    And the complete block does not exceed the final budget

  Scenario: Budget exhaustion reports omitted entries rather than hiding alphabetic tails
    Given more memory entries than the final index budget allows
    When the memories block is formatted
    Then it reports the shown and omitted counts against the total unique entries
    And it points to the complete discovery index using bounded offset and limit reads
    And it warns that indexes may be stale and exact entry files are authoritative
    And it supplies bounded root discovery when an index is missing
    And it does not cut filenames at the budget boundary
    And it drops relevance cues before it drops a listed entry
    And it preserves exact paths with whitespace or punctuation
    And it never recommends reading a symlinked discovery index
    And it rechecks an index replaced during entry reads before advertising its read path

  Scenario: Unchanged entry metadata is reused within a session
    Given loaded memory entries whose files are unchanged
    When the memories block is loaded again in the same process
    Then no entry file is opened again
    And the reuse returns the same filenames, sources, descriptions, and bodies
    And a rewritten in-place entry and an atomically replaced entry are read again
    And an entry replaced by a symlink is dropped instead of served from reuse

  Scenario: The project root probe is memoized per session
    Given a project whose memory root was resolved once
    When memory paths are resolved again for the same project
    Then the git root probe is not run again within its reuse window
    And an unavailable git probe disables public memory without failing the load

  Scenario: File limits do not hide the corpus size or weaken private precedence
    Given public and private roots with duplicate names and more entries than maxFiles
    When memories are loaded with a bounded file-read count and character budget
    Then private filenames win before the file-read limit is applied
    And the load result retains the total unique safe filenames and omitted count
    And unread or failed entries are not presented as loaded content
    And formatting reports file-limit omissions separately from budget omissions
    And discovery instructions preserve harness precedence for duplicate names

  Scenario: An impossibly small index budget cannot silently erase discovery
    Given a non-empty corpus and a budget too small for its omission notice and discovery pointer
    When the memories block is formatted
    Then it explicitly rejects the insufficient budget instead of returning an empty or oversized block

  Scenario: Rebuilt complete indexes include relevance metadata for unseen entries
    Given safe and private memory entries with descriptions including long legacy descriptions
    When the parent rebuilds MEMORY.md
    Then every strict regular filename retains its relative body link and private marker
    And every available description is included without the injection budget or maxFiles limit
    And bounded reads can page through the complete index
    And overlong metadata has an explicit notice and exact relative body link
    And unsafe symlinks and root replacement cannot publish outside content
    And a swapped-root cleanup cannot delete a replacement directory file
    And short descriptions leave space for complete longer descriptions when the total fits
    And entries without metadata consume only their complete filename links
    And memory loading itself never writes indexes or entry files

  Scenario: Entries without a description still appear in the index
    Given a memory entry with no description in its frontmatter
    When the memories block is formatted
    Then the index line lists the filename and source without inventing a description

  Scenario: Generated descriptions front-load routing cues without bloating planner protocols
    Given the package-owned selector and Memory consolidation prompts
    When the prompts are bound to the parent-provided task and identity
    Then generated Memory descriptions are single-line relevance cues of at most 120 characters
    And triggers precede supporting detail that belongs in the body
    And machine identity, schemas, read-only scope, privacy, evidence, and preservation-backed deletion rules remain explicit
    And the selector remains metadata-only with no tools or per-turn ranking
