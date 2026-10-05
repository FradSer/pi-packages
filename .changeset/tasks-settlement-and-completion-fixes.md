---
"@fradser/pi-tasks": patch
"@fradser/pi-agent-teams": patch
---

Return no result on a settlement that cannot continue in a session with no UI. The waiting and paused notices are transcript rows, so a headless `pi --print` run that ended with unfinished work printed nothing. A continuation result keeps its status message in every mode, because the model reads it on the next request.

Apply the completion holder check only while a task is in progress. A pending task is unheld, whatever a restore kept in `claimedBy`, so a restored pending task that names a departed holder completes through the fallback path instead of a refusal naming a holder who is gone. A task nobody ever took is still refused when the checks are on.

Clear `completionVerdict` and `completionGate` when an attempt fails. A failed attempt answered no gate, so a reader never sees an earlier attempt's verdict on a task whose current attempt failed.
