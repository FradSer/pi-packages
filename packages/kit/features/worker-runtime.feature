Feature: Shared worker-runtime primitives

  Pi-kit owns the file and environment mechanics that every package spawning or
  running inside a child Pi process needs: incremental bounded JSONL reads,
  capped atomic appends, atomic JSON replacement, the single-writer intent race,
  and an all-or-nothing required-environment binding. Domain validation, path
  layout, and coordination authority stay with the consumer.

  Diagnostics are parameterized by label so a consumer can adopt these without
  changing wording its own tests and operators already read.

  Rule: An incremental JSONL read never loses or replays a complete record

    Scenario: Records are read once and the offset advances past them
      Given a JSONL file holding three complete records
      When a batch is read from offset zero
      Then all three records are returned in file order
      And the returned offset is the byte length of the file
      And a second read from that offset returns no records

    Scenario: An unterminated trailing record is left for the next read
      Given a JSONL file whose last line has no newline yet
      When a batch is read
      Then only the complete records are returned
      And the offset stops before the unterminated record
      And the next read after the writer finishes returns that record

    Scenario: A truncated or recreated file restarts rather than skipping
      Given a stored offset larger than the current file size
      When a batch is read
      Then reading restarts from offset zero
      And callers deduplicate by record id rather than trusting the offset

    Scenario: A record larger than the batch cap cannot block the drain
      Given a single record larger than the batch cap
      When a batch is read
      Then no records are returned
      And the offset advances past the oversized chunk
      And a diagnostic reports that a malformed or unterminated record was consumed

    Scenario: A malformed JSON line is consumed and reported
      Given a file holding one valid record and one unparseable line
      When a batch is read
      Then the valid record is returned
      And a diagnostic reports that a malformed JSON record was consumed

    Scenario: A missing file is empty, not an error
      Given a path that does not exist
      When a batch is read
      Then no records and no diagnostics are returned
      And the offset is zero

  Rule: Appends and replacements are capped, private, and atomic

    Scenario: An appended record creates a private owner-only file
      Given a path inside a directory that does not exist yet
      When one record is appended
      Then the directory and file are created
      And a second append preserves the first record

    Scenario: An oversized record is refused rather than truncated
      Given a record larger than the configured cap
      When it is appended
      Then the call throws naming the cap
      And the error uses the caller's label
      And nothing is written

    Scenario: An atomic replacement leaves no temporary file
      Given a JSON file that already holds a value
      When it is replaced atomically
      Then a reader observes either the old or the new value, never a partial write
      And no temporary file remains beside it

  Rule: Exactly one racer publishes a given intent

    Scenario: Concurrent racers produce exactly one winner
      Given several concurrent processes claiming the same intent name
      When each attempts the exclusive create
      Then exactly one reports success
      And every other reports failure rather than throwing
      And one intent file exists

    Scenario: A caller-supplied name cannot escape its directory
      Given an intent name containing path traversal
      When the exclusive create runs
      Then the written file stays inside the intent directory
      And no file is created outside it

    Scenario: An oversized intent is refused
      Given an intent payload larger than the configured cap
      When the exclusive create runs
      Then the call throws naming the cap and the caller's label
      And no intent file and no temporary file remain

  Rule: Draining an intent never destroys an in-flight publish

    Scenario: Intents drain lowest name first and are removed
      Given a directory holding two valid intents
      When one intent is taken
      Then the lower-named intent is returned
      And its file is removed
      And taking again returns the other

    Scenario: A malformed intent is consumed with the consumer's reason
      Given a directory holding one intent that fails the consumer's validation
      When an intent is taken
      Then no intent is returned
      And the diagnostic names the file and carries the consumer's reason
      And the file is removed so it cannot block the queue

    Scenario: An unparseable intent younger than the grace is retried
      Given a directory holding a half-written intent file
      When an intent is taken
      Then no intent and no diagnostic are returned
      And the file survives for its author to finish publishing

    Scenario: An unparseable intent older than the grace is consumed
      Given a half-written intent file older than the publish grace
      When an intent is taken
      Then the diagnostic reports the unreadable intent using the caller's label
      And the file is removed

    Scenario: A missing directory is empty, not an error
      Given a directory that does not exist
      When an intent is taken
      Then no intent and no diagnostic are returned

    Scenario: The label parameter preserves existing consumer wording
      Given a consumer whose operators already read "malformed task intent"
      When that consumer passes its label
      Then the diagnostic reads exactly as it did before adoption

  Rule: A required environment binding is all-or-nothing

    Scenario: A complete binding is returned
      Given every required name is present and non-empty
      When the binding is read
      Then every name maps to its value

    Scenario: A missing name yields no binding at all
      Given one required name is absent
      When the binding is read
      Then the result is undefined rather than a partial binding

    Scenario: An empty value counts as missing
      Given one required name is present but empty
      When the binding is read
      Then the result is undefined
      And a partially configured child is treated as not a worker
