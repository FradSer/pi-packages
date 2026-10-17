---
"pi-matt-pocock": minor
---

Require a recommended option on `matt_pocock_ask` and always run a deadline that adopts it, so a question can never wait indefinitely.

`recommended` is now required and must copy one offered option; a call without it is refused before any dialog opens. Every ask arms one deadline (default 60 seconds, maximum 3600) that dismisses the selection and the custom-answer input through their abort signals, then returns the recommendation as the answer with `source: "timeout_recommended"`. Escape, cancellation, abort, no UI, and a blank custom answer still leave the decision pending and never adopt the recommendation. For an approval-required external or destructive action, recommend the option that does not act, because the deadline adopts it.