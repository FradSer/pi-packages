---
"@fradser/pi-recap": patch
---

Retry recap generation once when the model returns empty or generic verb-plus-identifier output, and discard the result if the retry remains uninformative.
