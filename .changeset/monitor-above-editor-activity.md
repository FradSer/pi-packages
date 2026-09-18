---
"@fradser/pi-monitor": minor
---

Show running monitors as above-editor live activity rows through pi-kit's shared widget instead of a footer status entry. Each running monitor contributes one row (`monitor · <description>`, Pi's native spinner cadence) that appears while the agent is idle waiting for the terminal result and disappears with the last terminal result or stop; the footer below the input no longer carries a monitor waiting count.