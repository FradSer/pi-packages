---
"pi-continual-learning": patch
---

Report the real applied Memory count in the `learn()` tool-result row. A real `~/Documents/Home Lab` run showed `[learning] settled · learned 0 Memory changes` next to a transcript row saying `Learning 2 memories applied`: `learningOutcomeSpec` renders `details.operations`, but `learn()` never put that field in its result details, so every applied run rendered zero. The tool result now carries the receipt's accumulated Memory operation count; proposals, failures and disabled results carry zero and keep their existing wording. No receipt, write or gate changes.
