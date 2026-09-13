# Context researcher

`context_get` is the package's sole Pi tool. It delegates a research request to a fresh Pi process with extension discovery disabled and only `read` and `bash` available. The prompt requires read-only behavior; `bash` can technically write because the child has no OS sandbox. The child may make a depth-1 clone of a public repository in a unique `/tmp` directory when source inspection is needed, then must remove that directory before completing.
