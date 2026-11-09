---
"@fradser/pi-kit": patch
---

Keep a normal-length live-activity identity intact on narrow terminals. The shared row layout previously reserved 12 columns for the activity unconditionally, so a 24-column terminal rendered `lea... · pnpm bui...` instead of the agent name. A short worker name now keeps its full width and the activity is ellipsized first; unusually long identities still reserve the activity's minimum columns so both parts remain readable. Applies to `learner`, `researcher`, `monitor` and every other consumer of `createLiveActivityWidget`. Both plain and markdown activity formats are covered at 24, 40, 48 and 120 columns.
