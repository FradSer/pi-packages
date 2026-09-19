# @fradser/pi-open-deskos

Report this machine's Pi sessions and their operating events to Open DeskOS, and optionally drive a Pi session that Open DeskOS hosts.

**English** | [简体中文](README.zh-CN.md)

Open DeskOS normally learns about Pi sessions by scanning a machine locally or over SSH. That direction is not always available, and a scan cannot see what a session is actually doing. This package inverts it: the machine that owns the sessions opens one **Desk Link** out to Open DeskOS and reports them itself.

A machine may also hold a **Control Credential** and become a **Console**: it opens a separate control connection to the same listener, lists the **Hosted Pi** sessions the desk hosts, launches new ones, attaches to them, steers a running turn, cancels it, ends the session, and reads its complete history on demand.

## Install

To install from this checkout, run the following from the repository root:

```bash
pi install "$(pwd -P)/packages/open-deskos"
```

The command records an absolute package path, so the checkout can live anywhere, including a directory with spaces. Keep the checkout in place; Pi loads the local files directly.

Once `@fradser/pi-open-deskos` is published, `pi install npm:@fradser/pi-open-deskos` replaces that path.

## Configure

A machine reports nothing until an address **and** a token are both set. A partially configured link stays silent. Control stays off until a separate control credential is also set. Run `/open-deskos` for configuration guidance.

```bash
export ODK_DESK_LINK_ADDRESS="192.168.88.161:8765"   # Open DeskOS Desk Link Service
export ODK_DESK_LINK_TOKEN="<per-link token>"
export ODK_DESK_LINK_MACHINE="desk-mac"              # optional, defaults to the hostname
export ODK_DESK_LINK_CONTROL_TOKEN="<control credential>"   # optional: makes this machine a Console
```

Put them in the environment Pi runs with (for a desktop session, the same place that starts `pi`). The control credential is never transmitted: the desk challenges with a one-time nonce and this machine answers with a proof over it.

## What is reported

- The current session's live identity, goal, activity, and events, plus other sessions registered on this machine in `directory-sessions` metadata (written by `pi-utils` and `pi-keyboard`). UUID and timestamp-prefixed UUID aliases merge into one session.
- State: `running` requires working metadata, a live Pi process, and timestamps compatible with that process's lifetime; live idle/settled records are `settled`. Dead/invalid/reused PIDs, unverifiable processes, and explicitly exited records are `exited`. One bounded process-table read (1 MiB, 2-second timeout) checks all PIDs; only the newest unambiguous session registered to a PID can be live. For the current session, Pi's own idle/agent events take precedence.
- Original metadata start/update times, optional session name, goal, and activity/recap. Scanning does not invent a new activity timestamp or read session histories.
- Bounded session events: the newest contiguous tail of at most 60 events and 262,144 UTF-8 bytes per session, counting text and tool names. User, thinking, tool-call, and assistant events remain single-line summaries capped at 200 characters.
- Tool results preserve their complete multiline Markdown, including tables, code fences, and whitespace, up to 65,536 UTF-8 bytes per result. All text parts are joined with two newlines; images and arbitrary result metadata are not sent. A result shortened at the byte limit carries `truncated: true` and never splits a Unicode code point. Its optional `toolName` is a separate 200-character summary, not a prefix inserted into the Markdown. Session activity remains a short first-line summary.

A change to these bounds is under way in this package's working tree. The desk's Desk Link Service enforces its own copy of the numbers above, so the two sides must be raised together; raising the reporter alone would be trimmed on the desk.

The inventory refreshes on session start and every 5 seconds after each scan, including while the link is offline. A refresh replaces only discovered entries: the current session's identity and events cannot be removed or overwritten by stale metadata. Shutdown/reload cancels refresh scheduling and invalidates pending results and reconnects.

At most 64 sessions are reported. Only the current session is pinned; other entries favor running, then settled, then exited state, with recency breaking ties. Newer metadata can refresh a formerly observed session resumed elsewhere without dropping its retained events. The cap can evict old history and its events—it is not an archive.

Each scan visits at most 256 workspaces, 2,048 JSON files, and 8,192 directory entries, reading at most 16 KiB per file. Malformed, oversized, linked, and non-regular files are skipped. Name, goal, and activity are limited to 200 characters each and may shorten further on the wire toward the 65,536-byte snapshot budget. Session IDs, exact working directories, workspace names, and timestamps are never shortened or collapsed. If exact identity fields still exceed that budget, the reporter omits whole lowest-priority entries from that snapshot and `/open-deskos` reports the omitted count. The current session is preserved. A single current identity larger than the frame budget cannot be represented without changing that identity; this remains a pathological limit.

The default registry is `~/.pi/agent/directory-sessions`. `PI_DIRECTORY_SESSIONS_DIR` selects an explicit registry; otherwise `PI_CODING_AGENT_DIR` (or legacy `PI_AGENT_DIR`) overrides the agent directory. Metadata writers must use the same registry. Discovery never edits or prunes registry files. Sessions without registry metadata are not invented, and removed metadata disappears on the next refresh unless this reporter observed that session directly.

## Driving a Hosted Pi

`/open-deskos` opens a menu, and its console row lists the Hosted Pi sessions the desk hosts, each with its state, goal, project, and age, and lets you launch a new one, attach to an existing one, send it a further instruction (including while a turn is running, which steers that turn rather than starting a second one), cancel the running turn, end the session, and read its complete history.

- **One Console drives one Hosted Pi.** Attaching replaces rather than shares any previous Console. Attaching is idempotent and repeatable by session identity, so a resumed Pi session can attach again.
- **Nothing is repeated and nothing is skipped.** An event's position is the position of the corresponding entry in the Hosted Pi's own session log. Attaching states the position last applied, reads history from there, and then consumes live events from that boundary onward. There is no replay window and no resync record to interpret.
- **The session outlives the connection.** A dropped control connection does not end a Hosted Pi: it keeps running, keeps its identity, and stays attachable.
- **Only a bounded tail enters your session.** Live events and the terminal result reach the assistant as a bounded summary; the complete content stays available on demand through the history tool and the console surface.
- **The desk stays in charge of itself.** While this machine drives a Hosted Pi, the desk names it in the Pi Sessions overview header, and local touch and keyboard keep working.
- **Tools.** The assistant can call `desk_*` tools to list, start, attach, prompt, cancel, end, and read history. The console surface owns its own keyboard input and never intercepts global terminal input.

## What is not

- **Reporting is never management.** A machine holding only the reporting token can report and nothing else: the package never sends a prompt, blocks a turn, or mutates a message on a reported session, and visibility through a Desk Link never makes a session controllable.
- **Control is a separate capability.** It needs the Control Credential, it never travels on the reporting connection, and a machine without it cannot become a Console.
- **No management of reported sessions.** Even as a Console, the package does not manage the sessions it reports. Control applies to Hosted Pi sessions the desk hosts, which are a different thing.
- **No answering a Hosted Pi mid-turn.** The desk's Pi host loads no extensions, and the SDK exposes no permission, approval, or ask-user surface, so a Hosted Pi cannot raise a request for you to answer. This is a limit of the host's configuration, not a missing feature.
- **No network discovery or pairing.** Local session metadata is discovered, but a machine that does not already know the address and token cannot register, and a Console must already know the control credential.
- **No history or credential scan.** The package does not read session histories, auth files, or arbitrary extra metadata of other sessions. Other sessions contribute registry metadata only, not synthetic events. Current-session tool-result text **is sent** within the bounds above; it may include file contents or sensitive output returned by a tool. Configure the link only when that sharing is intended.
- **No encryption.** The Desk Link is a plain connection to a LAN-only listener. The control credential is kept off the wire so a capture yields no reusable execution token, but content itself is not encrypted. Do not expose the Desk Link Service beyond the local network.

## Check the link from inside Pi

```
/open-deskos
```

The menu is the same in every configuration, and a row that is unavailable names the reason instead of disappearing. Its status row shows the link state, the machine identity, the endpoint, the reported session count, the event count, the control state, and the latest connection error when present; its console row opens the Hosted Pi list. Arguments are the fast path: `console`, `status`, `attach`, `launch`, `cancel`, and `history`. Diagnostics are command-only in every configuration: Open DeskOS adds no footer status line, custom footer, or working-directory suffix, even when offline or unconfigured.

## Behavior when the link drops

The reporter reconnects with a growing wait (1s, 2s, 4s … capped at 30s) and keeps exactly one link. Both retained history and pending events obey the per-session 60-event / 262,144-byte bounds. Each new connection sends the current session state and replays the complete retained event tail, even when there were no new offline events, because the service can forget machine state after its last link closes. Later flushes on that connection send only new events.

The control connection is separate and does not reproduce that behavior: list, launch, and history requests use a connection that closes after the answer, and a connection is held only while this machine is attached to a Hosted Pi. Losing it does not affect reporting, and it does not end the session on the desk.

## Wire contract

Newline-delimited JSON over one TCP connection, version 1 for reporting. Inventory sessions carry `discovered: true`; direct current-session observations do not. The service can therefore prefer active direct observations over later-written metadata from another reporter. The reporter writes `hello`, `sessions`, `events`, and `bye`; the service may reply `ack` or `error`. The `prompt` reply reserved in version 1 is still unimplemented, and control does not use it. Frames split on LF only and tolerate a trailing CR. Result events carry raw Markdown in `text`, plus optional `toolName` and `truncated: true`. Append-only event records are split between whole events into frames of at most 1 MiB, including JSON escaping and the final LF; bodies are never split or flattened to fit a frame. Replacing `sessions` snapshots retain their separate 65,536-byte producer budget. An event whose exact identity envelope alone makes it impossible to fit is not sent, and the command reports the frame-limit error.

Control uses version 2 on its own connection to the same listener. The handshake carries the protocol version and this session's identity alongside the machine name, so two Pi sessions on one machine are distinguishable Consoles. The console writes list, launch, attach, prompt, cancel, end, and history; the desk answers with state, event, acknowledgement, and error. A version the desk does not accept is refused by name rather than dropped. There is no detach record, no replay window, and no resync record.

## License

MIT