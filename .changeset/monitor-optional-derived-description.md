---
"@fradser/pi-monitor": minor
---

Let `monitor_start` omit `description`: the monitor derives a bounded human label from the command (whitespace collapsed, leading `sh -c` wrapper dropped, 60 characters maximum). Expanding the startup row now shows the success contract and any failure contract beside the command and monitor id, and the tool guideline replaces "declare the terminal result before starting" with explicit field roles so the description stops carrying the sentinel text.