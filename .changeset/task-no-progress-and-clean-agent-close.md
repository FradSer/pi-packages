---
"@fradser/pi-tasks": patch
"@fradser/pi-agent-teams": patch
---

Use one `tasks` transcript label for the four tools and settlement status messages. Display actions and readable statuses without changing tool names or structured data. Name expanded fields with `Description:` and `Verify:`, then show dependencies. Keep dependency previews in collapsed rows and bounded summaries in expanded status messages. Full continuation instructions stay in model context.

Return each unchanged task snapshot for continuation only once. Report waiting without another model request when no task progress occurs. Ignore timestamp-only writes when checking progress. Keep the three-continuation allowance for changed task state and preserve explicit recovery and authorization checks.

Keep a clean idle agent closure in the console mailbox when it owes no result or unread input and releases no unfinished work. Preserve stopped-state evidence without an unexpected-stop notification or another leader turn. Continue to report crashes, signals, unconfirmed input, unresolved results, unread current-incarnation mail, and interrupted work. Inspect unread mail without consuming it or changing delivery records. Treat malformed or incomplete unread records as unresolved input.
