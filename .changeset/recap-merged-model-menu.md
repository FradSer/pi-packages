---
"@fradser/pi-recap": patch
---

Drop the repeated current-recap text from the `/recap` menu title and merge the model override into one `Select recap model` option: dismissing the picker without choosing a model clears the stored override so recap generation falls back to the session default.