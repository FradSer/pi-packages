# Context Pi Package

**Version:** 0.5.1

`@fradser/pi-context` exposes one tool: `context_get`.

It starts an independent Pi child process for repository, library, codebase, and technical-topic research. This isolates exploratory tool calls from the main session while returning a concise, evidence-based result.

## Installation

```bash
pi install npm:@fradser/pi-context
# or from this repository:
pi install /path/to/pi-packages/packages/context
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

The child starts in a unique temporary working directory under `/tmp`. It is instructed to use only read-only investigation. If line-level evidence from a public repository is necessary, it may run `git clone --depth=1` in that directory, inspect the clone, and removes the entire temporary directory before completing. It must not modify the caller's working directory or run package-management, deployment, or interactive commands.

Results are bounded before entering the main session and render as compact, expandable context lifecycle rows.

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
