# Isolated context research workflow

Use `context_get` for a repository, library, codebase, or technical research request. It launches a stateless one-shot Pi worker so exploratory work and its tool calls do not enter the main session.

A package-local typed builder reads the bundled Markdown as a reference protocol and constructs a task-specific context-review prompt from the current request and working directory, then adds an explicit completion contract. The transcript identifies that execution with the normalized concrete request (`[context] research started · <research query>`), never with the Markdown path; while the async child runs, no duplicate progress row is rendered and live progress shows only in the researcher widget. The child has a `read,bash` allowlist and no extension discovery. The prompt requires read-only behavior and forbids edits, writes, package-manager commands, deployment, and interactive commands; `bash` can technically write because the child has no OS sandbox. For public repository evidence it may run `git clone --depth=1` into a unique directory under `/tmp`, inspect only the relevant files, cite the evidence in its answer, and remove the clone before it exits.

The returned answer should synthesize findings, distinguish facts from uncertainty, and cite useful source URLs or repository paths. It must not modify the caller's working directory.
