# @fradser/pi-session-control

Discover and send text to live Pi sessions without terminal input injection or session-file edits. Unix/macOS only, Node 20+.

## Install

```sh
pi install /absolute/path/to/pi-packages/packages/session-control
```

Load the extension in a new Pi process. Installation does not attach it to already-running sessions. For checkout development, run the executable `packages/session-control/bin/pi-session-control.mjs`; an npm installation exposes `pi-session-control` on PATH. The package is prepared for first publication, not assumed to exist on npm yet.

## Version 1 JSON-lines API

The CLI accepts no arguments. Send one newline-terminated JSON object per stdin line; stdout contains exactly one JSON object per response. Exit code is a transport/process result, not the command outcome: inspect `ok`. Do not place prompts in shell arguments.

```json
{"version":1,"requestId":"list-1","command":"list"}
{"version":1,"requestId":"status-1","command":"status","sessionId":"live-uuid"}
{"version":1,"requestId":"send-1","command":"send","sessionId":"live-uuid","text":"Please explain the failing test"}
```

List returns `{version,requestId,ok:true,sessions:[{sessionId,piSessionId,cwd,pid,name?,state}]}`. Status returns the same session object under `session`. State is `idle` or `running`; this bridge reports agent activity rather than individual UI prompts, so a user prompt can appear as running.

Send returns `{version,requestId,ok:true,sessionId,status:"accepted"|"queued"}`. **Neither status means completed**, nor does idle status prove a particular request succeeded. Pi's synchronous send API acknowledges submission, not eventual model success. Busy sessions default to `followUp`; optional `deliverAs:"steer"` requests steering. Prompt-template/command expansion stays disabled.

Errors have `{version:1,requestId:string|null,ok:false,error:{code,message}}`. Malformed requests may have a null requestId. An unavailable target returns `not_found`; a connection failure after submission is an **unknown outcome**. Retry only with the exact original requestId, target and payload. Never automatically select a different session.

`sessionId` is an opaque live-instance UUID and changes on reload, resume, new session, fork, or process restart. `piSessionId` identifies Pi's durable session for display, never routing. Re-list and explicitly select after any lifecycle change. This prevents replay into a later instance of the same durable session.

Identical send requestIds return their original receipt. Reusing one with another payload returns `request_conflict`. Receipts are kept for the whole live instance; after 10,000 unique sends, new requests fail closed (`capacity`) instead of evicting replay protection.

## Security and limits

Sockets live in `~/.pi/session-control` (override **both** processes with `PI_SESSION_CONTROL_DIR`). The directory must be user-owned, non-symlink, mode 0700; sockets are mode 0600. Keep its parent directories trusted. Same-user processes are trusted and can control sessions; this is not a sandbox or remote authentication service. No TCP listener is opened. pi-kit was inspected: it has no private-socket/framing helper, so this small transport uses Node built-ins.

Frames are limited to 65,536 bytes, text to 48,000 UTF-8 bytes, requestIds to 128 ASCII identifier characters, discovery to 128 socket entries, socket operations to 2 seconds, and stdin inactivity to 5 seconds. Socket paths must fit 100 UTF-8 bytes; use a short private directory when necessary. Stale sockets are ignored, never deleted by the CLI. Remove stale entries manually only while sessions are stopped if discovery hits capacity.

For SSH, run a fixed, trusted command such as `ssh -T -o BatchMode=yes -o ConnectTimeout=5 host /absolute/path/to/pi-session-control` with the JSON piped through stdin. Configure the host and executable outside model-controlled data. The voice integration may use `PI_SESSION_CONTROL_COMMAND` to choose its executable; this CLI itself only reads `PI_SESSION_CONTROL_DIR`.

## Verification

```sh
pnpm exec tsx --test packages/session-control/tests/*.test.ts
python3 -m pytest packages/session-control/tests -q
pnpm exec tsc --noEmit -p tsconfig.extensions.json
```
