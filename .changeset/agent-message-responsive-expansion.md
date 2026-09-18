---
"@fradser/pi-agent-teams": patch
"@fradser/pi-kit": patch
---

Render coordination message previews against the actual terminal width rather than a fixed character limit, reserving the complete configured expansion hint. Expanded message rows wrap the full message inline after the recipient and outcome exactly once instead of repeating a clipped preview above a duplicate body. Preserve semantic line breaks, native theme bands, and safe display text, including visible labels inside terminal OSC-8 hyperlinks. Keep literal JSON empty strings, punctuation spacing, and quoted newlines intact by separating handle replacement from prose cleanup. Reuse the same pi-kit lifecycle abstraction as context research; native Ctrl+O, mouse expansion, and terminal resizing are covered by isolated Pi integration tests.
