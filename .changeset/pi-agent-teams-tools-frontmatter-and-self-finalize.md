---
"@fradser/pi-agent-teams": patch
---

Honor multi-line YAML tool lists in agent frontmatter and make unfinalized teammate reports self-finalize before escalating. `parseFrontmatter` now parses dash-list `tools:` blocks — flush-left or indented items, interleaved blank/comment lines, no-space `-item` entries — which previously collapsed silently into an empty execution allowlist. When a teammate's sequence ends while its last leader-bound report lacks terminal status, the machine drains outboxes before deciding, sends one inbox finalize request per spawn incarnation instructing `status="completed"`/`status="failed"`, escalates to the leader reminder only on a second miss, cleans up nudge bookkeeping on every shutdown path, and the worker-side `send_message` result reminds when a leader-bound message carries no terminal status.
