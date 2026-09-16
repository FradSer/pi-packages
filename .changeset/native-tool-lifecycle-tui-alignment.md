---
"@fradser/pi-kit": patch
"@fradser/pi-agent-teams": patch
"@fradser/pi-monitor": patch
"@fradser/pi-utils": patch
"@fradser/pi-impeccable": patch
"pi-matt-pocock": patch
---

Align tool lifecycle TUI styling with Pi native tokens: partial results render on toolPendingBg with warning accents, settled results on toolSuccessBg with success accents, and errors on a symmetrical toolErrorBg band whose subject is the first error line with remaining lines as expandable details (no duplicated subject). Remove the renderError escape hatch so every consumer error renders through the shared band, and style interactive model-picker query input in native blue
