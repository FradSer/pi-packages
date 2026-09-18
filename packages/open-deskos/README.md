# @fradser/pi-open-deskos

Report this machine's Pi sessions and their operating events to Open DeskOS.

**English** | [简体中文](README.zh-CN.md)

Open DeskOS normally learns about Pi sessions by scanning a machine locally or over SSH. That direction is not always available, and a scan cannot see what a session is actually doing. This package inverts it: the machine that owns the sessions opens one **Desk Link** out to Open DeskOS and reports them itself.

## Install

To install from this checkout, run the following from the repository root:

```bash
pi install "$(pwd -P)/packages/open-deskos"
```

The command records an absolute package path, so the checkout can live anywhere, including a directory with spaces. Keep the checkout in place; Pi loads the local files directly.

Once `@fradser/pi-open-deskos` is published, `pi install npm:@fradser/pi-open-deskos` replaces that path.

## Configure

A machine reports nothing until an address **and** a token are both set. A partially configured link stays silent. Run `/open-deskos` for configuration guidance.

```bash
export ODK_DESK_LINK_ADDRESS="192.168.88.161:8765"   # Open DeskOS Desk Link Service
export ODK_DESK_LINK_TOKEN="<per-link token>"
export ODK_DESK_LINK_MACHINE="desk-mac"              # optional, defaults to the hostname
```

Put them in the environment Pi runs with (for a desktop session, the same place that starts `pi`).

## What is reported

- The current session's live identity, goal, activity, and events, plus other sessions registered on this machine in `directory-sessions` metadata (written by `pi-utils` and `pi-keyboard`). UUID and timestamp-prefixed UUID aliases merge into one session.
- State: `running` requires working metadata, a live Pi process, and timestamps compatible with that process's lifetime; live idle/settled records are `settled`. Dead/invalid/reused PIDs, unverifiable processes, and explicitly exited records are `exited`. One bounded process-table read (1 MiB, 2-second timeout) checks all PIDs; only the newest unambiguous session registered to a PID can be live. For the current session, Pi's own idle/agent events take precedence.
- Original metadata start/update times, optional session name, goal, and activity/recap. Scanning does not invent a new activity timestamp or read session histories.
- Bounded session events: the newest contiguous tail of at most 60 events and 262,144 UTF-8 bytes per session, counting text and tool names. User, thinking, tool-call, and assistant events remain single-line summaries capped at 200 characters.
- Tool results preserve their complete multiline Markdown, including tables, code fences, and whitespace, up to 65,536 UTF-8 bytes per result. All text parts are joined with two newlines; images and arbitrary result metadata are not sent. A result shortened at the byte limit carries `truncated: true` and never splits a Unicode code point. Its optional `toolName` is a separate 200-character summary, not a prefix inserted into the Markdown. Session activity remains a short first-line summary.

The inventory refreshes on session start and every 5 seconds after each scan, including while the link is offline. A refresh replaces only discovered entries: the current session's identity and events cannot be removed or overwritten by stale metadata. Shutdown/reload cancels refresh scheduling and invalidates pending results and reconnects.

At most 64 sessions are reported. Only the current session is pinned; other entries favor running, then settled, then exited state, with recency breaking ties. Newer metadata can refresh a formerly observed session resumed elsewhere without dropping its retained events. The cap can evict old history and its events—it is not an archive.

Each scan visits at most 256 workspaces, 2,048 JSON files, and 8,192 directory entries, reading at most 16 KiB per file. Malformed, oversized, linked, and non-regular files are skipped. Name, goal, and activity are limited to 200 characters each and may shorten further on the wire toward the 65,536-byte snapshot budget. Session IDs, exact working directories, workspace names, and timestamps are never shortened or collapsed. If exact identity fields still exceed that budget, the reporter omits whole lowest-priority entries from that snapshot and `/open-deskos` reports the omitted count. The current session is preserved. A single current identity larger than the frame budget cannot be represented without changing that identity; this remains a pathological limit.

The default registry is `~/.pi/agent/directory-sessions`. `PI_DIRECTORY_SESSIONS_DIR` selects an explicit registry; otherwise `PI_CODING_AGENT_DIR` (or legacy `PI_AGENT_DIR`) overrides the agent directory. Metadata writers must use the same registry. Discovery never edits or prunes registry files. Sessions without registry metadata are not invented, and removed metadata disappears on the next refresh unless this reporter observed that session directly.

## What is not

- **No management.** v1 is report-only. The package never sends a prompt, blocks a turn, or mutates a message, and visibility through a Desk Link never makes a session controllable.
- **No network discovery or pairing.** Local session metadata is discovered, but a machine that does not already know the address and token cannot register.
- **No history or credential scan.** The package does not read session histories, auth files, or arbitrary extra metadata. Other sessions contribute registry metadata only, not synthetic events. Current-session tool-result text **is sent** within the bounds above; it may include file contents or sensitive output returned by a tool. Configure the link only when that sharing is intended.
- **No encryption.** The Desk Link is a plain connection to a LAN-only listener, and the token is the gate. Do not expose the Desk Link Service beyond the local network.

## Check the link from inside Pi

```
/open-deskos
```

Shows the link state, the machine identity, the endpoint, the reported session count, the event count, and the latest connection error when present. Diagnostics are command-only: Open DeskOS adds no footer status line, custom footer, or working-directory suffix, even when offline or unconfigured.

## Behaviour when the link drops

The reporter reconnects with a growing wait (1s, 2s, 4s … capped at 30s) and keeps exactly one link. Both retained history and pending events obey the per-session 60-event / 262,144-byte bounds. Each new connection sends the current session state and replays the complete retained event tail, even when there were no new offline events, because the service can forget machine state after its last link closes. Later flushes on that connection send only new events.

Version 1 has no event IDs or replay acknowledgement. If another link kept the service's machine state alive, reconnect replay can duplicate retained events; it does not guarantee exactly-once delivery. Replay remains bounded and is not a session archive.

## Wire contract

Newline-delimited JSON over one TCP connection, version 1. Inventory sessions carry `discovered: true`; direct current-session observations do not. The service can therefore prefer active direct observations over later-written metadata from another reporter. The reporter writes `hello`, `sessions`, `events`, and `bye`; the service may reply `ack`, `error`, or a reserved `prompt` record that nothing implements yet. Frames split on LF only and tolerate a trailing CR. Result events carry raw Markdown in `text`, plus optional `toolName` and `truncated: true`. Append-only event records are split between whole events into frames of at most 1 MiB, including JSON escaping and the final LF; bodies are never split or flattened to fit a frame. Replacing `sessions` snapshots retain their separate 65,536-byte producer budget. An event whose exact identity envelope alone makes it impossible to fit is not sent, and the command reports the frame-limit error.

## License

MIT
