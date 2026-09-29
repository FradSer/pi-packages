---
"pi-open-deskos": minor
---

A desk's voice agent can drive the Pi session this machine is running, from inside that session, with no process installed.

The package now serves the task protocol a desk's voice agent already speaks — `list`, `status`, `prompt` and `cancel` — on a private Unix socket, and `start`/`launch`/`end`/`history` are refused with one fixed reason because a session is not a session host. The endpoint is created from `session_start` and withdrawn from `session_shutdown`, in a `0700` directory with a `0600` socket and a `0600` descriptor beside it. Ownership of the file is the only gate: there is no token, no second credential, and nothing listens on the network.

**What changed**

- The endpoint is per session, at `<directory>/<sessionId>.sock`, and each session publishes `<sessionId>.json` with its own socket, project and state. One endpoint per host served whichever session bound it first and refused every later one, which is the opposite of what a desk needs when the operator has several sessions and means one of them by its project.
- The endpoint is opt-in through `ODK_SESSION_HOST_SOCKET`, which names the directory this machine's session sockets live in. An endpoint that lets something else hand a session work is a capability a machine declares, not a default it inherits.
- `session-control` is a POSIX shell launcher a desk runs on the far side of its own SSH session. It finds a node runtime itself — a login session's PATH is not the one an interactive shell has, and a machine where node is a version manager's install answers nothing to a client that assumed otherwise — and execs the relay beside it.
- The relay speaks the frame contract on standard input and standard output. With no socket named it resolves the session from the request's own project; a project no session serves is answered with the protocol's own refusal rather than with some other session's reply.
- The listening server is unref'd, because an endpoint a desk can reach is never a reason a Pi process stays alive.
