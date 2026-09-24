---
"pi-open-deskos": minor
---

Report the call identity Pi wrote and the error flag Pi recorded alongside each tool call and tool result, so a desk can pair a result with its own call and colour the tool box from Pi's record instead of from event order. Both fields survive the reporter's body bound, are emitted only for the kinds that carry them, and stay absent when Pi's message has no identity, which keeps a consumer that does not read them working unchanged.
