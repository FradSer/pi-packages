# 0003: Auto-memory injects an index, not full entries

## Status

Accepted

## Context

continual-learning injects every project memory entry's full text into the
system prompt on every turn, capped at 96K chars. Measured with a request-body
mitm in the pi-packages workspace, this accounted for roughly 60K chars
(~15K tokens) per request. Every new leader session and every teammate child
pays the full price; gateway prefix caching only amortizes repeat turns within
one session.

## Decision

`before_agent_start` injects only the memory index (filename, source, and a
one-line description per entry). Full entry content is no longer injected;
the model reads specific memory files with `read` when a task needs them.
A bounded budget applies to the index itself.

## Consequences

- Per-turn context drops by ~10-15K tokens in memory-heavy projects.
- Tasks that implicitly relied on all memories being in context must now read
  memory files explicitly; the guidance text injected with the index says so.
- The 96K full-text budget is replaced by a small index budget (filenames plus
  one-line descriptions), so entry count no longer scales the prompt.
