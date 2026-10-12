---
"@fradser/pi-tasks": minor
---

Make creating a task lighter and the tool surface smaller.

**What changed**

- A `subject` is a short name of at most 60 characters. `create_task` and `update_task` refuse a longer subject and point at `description`. The store and its internal callers stay permissive, so Agent Teams keeps creating its generated work records.
- `description` and `verify` are documented as optional; a subject alone is a complete task. The previous wording told the model to put the full brief in `description`, which made every creation carry a paragraph.
- The four tool descriptions and every parameter description were trimmed. The registered surface is about 6044 characters instead of 7482, roughly 1510 tokens instead of 1870, sent on every request. The `update_task` context schema is about a third shorter.

Contract: `features/discoverability.feature`, `features/work-domain.feature`.

**Verification**

- `tests/test_task_contents.py` refuses a 61-character subject with a message naming the limit, accepts 60, and refuses a long rename.
- `tests/test_discoverability.py` asserts the tool surface states the short-name rule, the limit, that a subject alone is complete, and that detail goes in `description` only when it does not fit.
- `tests/test_list_titles.py` creates its long-title fixture through the store, because the model-facing tool no longer accepts that subject.
- The tasks suite and the Agent Teams consumer suite pass.