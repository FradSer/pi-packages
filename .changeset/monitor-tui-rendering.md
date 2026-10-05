---
"@fradser/pi-monitor": patch
---

Keep terminal state visible before long console descriptions, expose all keys in
scrollable help with a width-aware footer, and refresh running human-only output
while the console is open. Clear refresh timers when the overlay closes.

Decode Kitty and xterm printable shortcuts through Pi v1 APIs while ignoring releases and
control-modified input.
