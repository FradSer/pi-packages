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

The child runs in the caller's working directory through pi-kit's minimal `runPiWorker` mode: `-ne -ns -np -nc --no-themes` disables extension, skill, prompt-template, context-file, and theme discovery, while `--tools read,bash` exposes only the two required tools. It has no sandbox, timeout, or display truncation; `bash` remains technically able to write because there is no OS sandbox, so the bundled worker prompt requires no modifications. If line-level evidence from a public repository is necessary, it may use `git clone --depth=1` under `/tmp` with removal after inspection. It must not run package-management, deployment, or interactive commands. The shared worker fails closed if its bounded stdout, stderr, or JSONL line limits are exceeded.

A package-local typed builder reads the bundled Markdown as a reference protocol and builds a task-specific context-review prompt containing the caller working directory, complete research request, reference protocol, and completion contract. The Markdown file itself is never used as an execution identity. Startup renders `[context] research started · <research query>`, using the normalized concrete query that produced the prompt; the row remains width-bounded and does not expose the resource path. While the async child runs, the transcript keeps only that started row with no duplicate progress row; live progress shows in the researcher widget above the editor. The widget shows neutral live research activity. The child always runs with `--no-session`, so separate invocations retain no memory or agent-teams state. A successful empty answer is retried exactly once with a stronger completion requirement that does not rely on hidden reasoning or prior tool output. Results enter the main session untruncated and render as a compact, expandable `[context] researched` lifecycle row.

## Structure

```text
context/
├── index.ts
├── extensions/context-tools.ts
├── extensions/context-command.ts
├── references/workflow.md
├── extensions/context-prompt.ts
└── prompts/context-research.md
```

## License

MIT
