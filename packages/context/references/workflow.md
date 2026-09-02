# Isolated context research workflow

Use `context_get` for a repository, library, codebase, or technical research request. It launches a separate Pi process so exploratory work and its tool calls do not enter the main session.

The child is read-only: it can use `read` and `bash`, but never `edit` or `write`. For public repository evidence it may run `git clone --depth=1` into a unique directory under `/tmp`, inspect only the relevant files, cite the evidence in its answer, and remove the clone before it exits.

The returned answer should synthesize findings, distinguish facts from uncertainty, and cite useful source URLs or repository paths. It must not modify the caller's working directory.
