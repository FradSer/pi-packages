## Unreleased

## 0.4.0

### Minor Changes

- 0c9bea5: A desk's voice agent can drive the Pi session this machine is running, from inside that session, with no process installed.
  
  The package now serves the task protocol a desk's voice agent already speaks — `list`, `status`, `prompt` and `cancel` — on a private Unix socket, and `start`/`launch`/`end`/`history` are refused with one fixed reason because a session is not a session host. The endpoint is created from `session_start` and withdrawn from `session_shutdown`, in a `0700` directory with a `0600` socket and a `0600` descriptor beside it. Ownership of the file is the only gate: there is no token, no second credential, and nothing listens on the network.
  
  **What changed**
  
  - The endpoint is per session, at `<directory>/<sessionId>.sock`, and each session publishes `<sessionId>.json` with its own socket, project and state. One endpoint per host served whichever session bound it first and refused every later one, which is the opposite of what a desk needs when the operator has several sessions and means one of them by its project.
  - The endpoint is opt-in through `ODK_SESSION_HOST_SOCKET`, which names the directory this machine's session sockets live in. An endpoint that lets something else hand a session work is a capability a machine declares, not a default it inherits.
  - `session-control` is a POSIX shell launcher a desk runs on the far side of its own SSH session. It finds a node runtime itself — a login session's PATH is not the one an interactive shell has, and a machine where node is a version manager's install answers nothing to a client that assumed otherwise — and execs the relay beside it.
  - The relay speaks the frame contract on standard input and standard output. With no socket named it resolves the session from the request's own project; a project no session serves is answered with the protocol's own refusal rather than with some other session's reply.
  - The listening server is unref'd, because an endpoint a desk can reach is never a reason a Pi process stays alive.

### Patch Changes

- 8d2939b: Preserve actual persisted assistant entry IDs and stop reasons in Open DeskOS reporting. Send live completion metadata after settlement and use the same IDs during replay. Do not promote aborted, stale, or nonterminal messages to completed turns.
- 842b92e: A tool call now names its pattern instead of the directory it searched.
  
  Pi's built-in `grep` and `find` take `{ pattern, path? }`, and every package that labeled a tool call from its arguments read `path` first, so a search that named a root rendered as that directory (`file: <directory>`, `grep: <directory>`, or `<tool> <directory>`) while a search without a root fell back to the bare tool name. The pattern is what the call is doing; the path is only where it looked.
  
  **@fradser/pi-kit**
  
  - `classifyToolActivity()` and `inlineToolActivity()` are new exports: one precedence rule — an explicit command, then a search's pattern, then a path, a query, a subject, and a delivery target — shared by every labeling call site instead of restated per package.
  - Live worker progress labeled a `grep` or `find` call `file: <directory>` whenever it carried a `path`, and fell back to the bare tool name otherwise. It now reports `search: <pattern>` and keeps `file: <name>` for genuine file reads.
  
  **@fradser/pi-agent-teams**
  
  - A teammate running `grep`/`find` with a `path` showed `file: <directory>` in its live activity row. It now renders `search: <pattern>`, and its labeler consumes the shared classifier rather than keeping its own copy of the ordering.
  
  **pi-open-deskos**
  
  - `summarizeToolCall` ignored `pattern` entirely, so a `grep` call read as `grep: <directory>`. It now renders `search: <pattern>` and still prefers an explicit command, then a path, for every other tool.
  
  **pi-continual-learning**
  
  - The dreaming widget showed a `grep`/`find` call as `<tool> <directory>`, because a consolidation worker holds `grep`, `find`, and `ls` alongside `read`. A search now names its pattern, and the label is the testable `dreamingToolActivity()` rather than inline argument parsing.
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [ff9b7ff]
- Updated dependencies [2bba220]
- Updated dependencies [426ef90]
- Updated dependencies [6603d43]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [6416992]
- Updated dependencies [fc0d801]
- Updated dependencies [53cb34f]
- Updated dependencies [ceb8e23]
- Updated dependencies [842b92e]
- Updated dependencies [b3daa7f]
- Updated dependencies [e86a44f]
- Updated dependencies [e86a44f]
- Updated dependencies [842b92e]
- Updated dependencies [e86a44f]
- Updated dependencies [53cb34f]
- Updated dependencies [53cb34f]
  - @fradser/pi-kit@0.6.0

- A desk's voice agent can drive the Pi session this machine is running. When `ODK_SESSION_HOST_SOCKET` names a directory, every session on this machine publishes its own endpoint from `session_start` and withdraws it on `session_shutdown`, serving the task protocol a desk already speaks: `list`, `status`, `prompt` and `cancel`, with `start`/`launch`/`end`/`history` refused as a session that is not a session host. Each session has its own socket and descriptor, so several sessions on one machine are all reachable and none is refused for an endpoint another holds. The `session-control` launcher finds a node runtime itself, because a login session's PATH is not the one an interactive shell has, and resolves the session from the request's project when no socket is named.

# pi-open-deskos

## 0.3.0

### Minor Changes

- e4c8e2b: Report the call identity Pi wrote and the error flag Pi recorded alongside each tool call and tool result, so a desk can pair a result with its own call and colour the tool box from Pi's record instead of from event order. Both fields survive the reporter's body bound, are emitted only for the kinds that carry them, and stay absent when Pi's message has no identity, which keeps a consumer that does not read them working unchanged.

## 0.2.1

### Patch Changes

- Updated dependencies [52e25f9]
  - @fradser/pi-kit@0.5.1

## 0.2.0

### Minor Changes

- b0231e3: Report this machine's Pi sessions and their operating events to Open DeskOS over a
  package-initiated Open DeskOS Link. The package observes the session lifecycle and message
  stream in process, bounds every retained event exactly like the runtime's local
  collector (60 per session, one single line each, tool results reduced to their first
  line), reconnects with a growing capped wait, and holds one bounded snapshot across an
  outage. An unconfigured or partially configured machine stays silent, and v1 is
  report-only: it never sends a prompt, blocks a turn, or mutates a message.

### Patch Changes

- b0231e3: Remove automatic Open DeskOS Link footer status updates in every configuration and connection state. Keep reporting unchanged and expose link and configuration diagnostics through `/odk` only.
- 5dda2df: Document local installation from any checkout using a quoted absolute package path,
  without relying on a personal home-directory layout. Verify both language recipes
  in a disposable checkout whose path contains spaces.
- Updated dependencies [b0231e3]
- Updated dependencies [ac83f4e]
- Updated dependencies [9cabb0d]
- Updated dependencies [919504f]
- Updated dependencies [bcb0054]
- Updated dependencies [efd5641]
- Updated dependencies [919504f]
- Updated dependencies [274cc90]
- Updated dependencies [28bdae2]
- Updated dependencies [707c4c5]
- Updated dependencies [5b4f51b]
- Updated dependencies [b0231e3]
- Updated dependencies [552a083]
- Updated dependencies [efd5641]
  - @fradser/pi-kit@0.5.0
