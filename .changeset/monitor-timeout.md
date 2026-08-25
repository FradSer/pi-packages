---
"@fradser/pi-monitor": minor
---

Add bounded monitor timeouts. `monitor_start` accepts `timeout_ms` and emits a terminal `timeout` result after the deadline, stopping the process group instead of waiting indefinitely when an external CLI or API is unavailable.
