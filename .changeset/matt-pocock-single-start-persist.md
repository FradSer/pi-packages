---
"pi-matt-pocock": patch
---

Persist a started workflow's state exactly once, carrying the procedure-delivery set that its first step shows. Starting a workflow previously wrote two state entries — one without the delivery set and one with — so a restored session read two beginnings and a consumer comparing the persisted record against the delivered message details saw them disagree. The guidance sentence also names the contract term the delivery bundles use, "blocking reviews", instead of a singular rewording of it.
