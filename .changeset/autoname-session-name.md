---
"@fradser/pi-utils": minor
---

`/autoname` names the current session with the current model.

Pi's own `/name` answers `Usage: /name <name>` when it is submitted with no
argument and no name set. `/autoname` is the model-generated counterpart: it
reads what the session is about and applies a short, recognizable display name.

**Why a new command**

`/name` is compiled into the interactive mode. Its branch runs before
extension commands are consulted, and Pi exposes no hook to intercept it, so an
extension cannot give it a model-generated argumentless behavior. `/name
<name>` still sets an explicit name; `/autoname` is for the case where you do
not want to type one.

**What it does**

- Builds its digest from the user's own requests only, so the name describes the
  task instead of the assistant's wording, and bounds the digest to a fixed
  character budget.
- Steers the name with an optional argument: `/autoname release notes rewrite`.
- Reduces the model answer to a plain display name. Quoting, markdown, list
  markers, and any sentence after the first line are dropped; an over-long name
  is cut at a word boundary.
- Sends a bounded one-shot request: no tools, at most 64 output tokens, no
  caching, and the current session id forwarded so conversation-routing gateways
  accept the nested call.

**Failure behavior**

Generation always settles. A 20-second deadline, an aborted session, a missing
model, absent credentials, a provider rejection, and an unusable answer each
report their own cause. The deadline races the request rather than only
signalling it, so a provider that ignores its abort signal cannot hold the
command open, and each failure is reported as a reported failure rather than an
unhandled rejection. A provider rejection arrives as a message carrying
`stopReason: "error"` rather than as a thrown error, and is no longer reported
as a credential problem.