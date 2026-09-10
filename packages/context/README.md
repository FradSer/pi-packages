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
pi --print --mode json --no-session --tools read,bash --exclude-tools edit,write
```

The child runs in the caller's working directory with no sandbox, no timeout, and no truncation, launched through pi-kit's shared `runPiWorker`. It is instructed to use only read-only investigation. If line-level evidence from a public repository is necessary, the prompt suggests `git clone --depth=1` under `/tmp` with removal after inspection. It must not run package-management, deployment, or interactive commands.

Results enter the main session untruncated and render as compact, expandable context lifecycle rows.

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
