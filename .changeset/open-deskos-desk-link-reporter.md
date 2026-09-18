---
"@fradser/pi-open-deskos": minor
---

Report this machine's Pi sessions and their operating events to Open DeskOS over a
package-initiated Desk Link. The package observes the session lifecycle and message
stream in process, bounds every retained event exactly like the runtime's local
collector (60 per session, one single line each, tool results reduced to their first
line), reconnects with a growing capped wait, and holds one bounded snapshot across an
outage. An unconfigured or partially configured machine stays silent, and v1 is
report-only: it never sends a prompt, blocks a turn, or mutates a message.
