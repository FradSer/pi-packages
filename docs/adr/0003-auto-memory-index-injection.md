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

`before_agent_start` supplies a hidden untrusted reference message containing only the memory index (filename and a
one-line description per entry). Full entry content is no longer injected;
the model reads specific memory files with `read` when a task needs them.
A bounded budget applies to the index itself. As of the 2026-10-09 safety repair, variable metadata stays out of the system prompt; only the fixed retrieval protocol is added there. A context hook removes stale references and retains one current index. Entry bodies remain on-demand reference data, never instruction authority. This change does not establish model-level prompt-injection immunity.

## Consequences

- Per-turn context drops by ~10-15K tokens in memory-heavy projects.
- Tasks that implicitly relied on all memories being in context must now read
  memory files explicitly; the guidance text injected with the index says so.
- The 96K full-text budget is replaced by a small index budget (filenames plus
  one-line descriptions), so entry count no longer scales the prompt.

## 2026-10-10 bounded retrieval amendment

The index remains the discovery surface. A lexical metadata ranker may now add
at most three complete relevant bodies, at most 4,000 characters each and 8,000
characters including the full reference block. Large or incomplete entries remain
on-demand reads. Bodies and revision hashes stay in the hidden untrusted message;
current user instructions and verified evidence take precedence. Recent exposure
can nominate an existing entry for correction, but is never factual evidence.
This removes the assumption that every model reliably opens relevant files. It
does not establish useful recall, correct application, or prompt-injection resistance;
those require real downstream task evidence and include retrieval/learning costs.

## 2026-10-12 compact retained-reference amendment

This supersedes the bounded automatic-body retrieval amendment above. Injection
contains deduplicated filenames and one-line descriptions only. The private copy
wins across roots; per-entry source suffixes are omitted. A single compact roots
list permits actual on-demand reads. Omission counts and complete-index pointers
appear only when entries are omitted; shortened metadata remains marked.

An unchanged reference stays in its existing context position instead of being
appended after every user message. Changed indexes replace stale references;
branching or compaction restores a missing current reference. Empty discovery
removes obsolete references. This avoids redundant session entries and preserves
the unchanged prefix. Actual body reads, correction, and downstream benefit still
require separate evidence; listing metadata does not establish Memory use.
