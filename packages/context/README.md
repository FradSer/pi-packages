# @fradser/pi-context

`@fradser/pi-context` exposes one tool: `context_get`.

It starts an independent Pi child process for repository, library, codebase, and technical-topic research. This isolates exploratory tool calls from the main session while returning a concise, evidence-based result.

## Installation

```bash
pi install npm:@fradser/pi-context
```

## Usage

Use natural language to ask Pi for research or external context:

```text
Research how facebook/react implements server actions.
Compare the current React Router and Next.js data-loading guidance.
Investigate https://github.com/owner/repo and explain its architecture.
```

Pi recognizes these requests and invokes `context_get` automatically. Users do not need to type `context_get` or use a slash command directly; it is an internal native tool with one `query` parameter containing the context request.

## Child-process constraints

The child runs as:

```text
pi --print --mode json --no-session -ne -ns -np -nc --no-themes --tools read,bash
```

The child runs in the caller's working directory through pi-kit's minimal `runPiWorker` mode: `-ne -ns -np -nc --no-themes` disables extension, skill, prompt-template, context-file, and theme discovery, while `--tools read,bash` exposes only the two required tools. It has no sandbox, timeout, or display truncation; `bash` remains technically able to write because there is no OS sandbox, so the bundled agent prompt requires no modifications. If line-level evidence from a public repository is necessary, it may use `git clone --depth=1` under `/tmp` with removal after inspection. It must not run package-management, deployment, or interactive commands. The shared worker fails closed if its bounded stdout, stderr, or JSONL line limits are exceeded.

Each run is presented as a uniquely named sub-agent. Pi-kit's package-agent helper loads the prompt bundled by this package at `agents/context-researcher.md`; no project `.agents` directory is used. Startup renders `[agent] @context-<id> started · agents/context-researcher.md`, while the widget above the editor shows that same identity and its latest tool, thinking, or answer activity. Results enter the main session untruncated and render as compact, expandable context lifecycle rows.

## Structure

```text
context/
├── index.ts
├── extensions/context-tools.ts
├── extensions/context-command.ts
├── references/workflow.md
└── agents/context-researcher.md
```

## License

MIT
