# Docker acceptance evidence

`tests/skill_router_docker.sh` builds an isolated tree from packed tarballs and runs
the whole acceptance inside `node:24-bookworm-slim`: the package gate, a real
collection install through the router, and both scripted end-to-end assemblies.

Latest run: 2026-10-21, Pi 1.3.0, Bun 1.4.1, base image `node:24-bookworm-slim`
(linux-arm64), skill-router tarball
`b174bce95f0cdc714d08a16b40a1803e92584ac9b08613c9035b9dab1ba19efd`, kit tarball
`8c0005948aba17d3dc3a35f413625ac5d822c9b1b2e4c7e753c465fd56a991bf`.

## What the container showed

- `pi list` loads exactly one package, the packed `pi-skill-router`; no other
  workspace package is present in the isolated tree.
- The package gate ran `pytest packages/skill-router/tests/ -q` → 101 passed.
- Installing a collection ran the real path: a local Git repository cloned into the
  cache, both skills materialized under `exposed/collections/upstream/leaves/`, and
  the registry written.
- `codemode` assembly: `searchTools("seo audit")` returned
  `skill_router__upstream__seo_audit` and `skill_router__upstream__release_notes`;
  the call resolved to `ok: true`, `truncated: false`, a 182-character body and the
  skill directory; the routing suggestion was absent, as the tools channel requires.
- `fallback` assembly: the same prompt produced the routing suggestion naming the
  leaf `SKILL.md`, and no `codemode` call ran.

## Two portability gaps the container found

Both were environment requirements of the package's own suite, not product defects,
and the script now satisfies them instead of skipping anything:

1. **Bun is a declared requirement.** CI pins Bun 1.4.1, and
   `test_registry_reuse_is_keyed_on_file_identity` reads the module through
   `bun -e`. The first container run failed on `FileNotFoundError: 'bun'`. The
   setup installs Bun 1.4.1 with the official installer; npm's `bun` postinstall
   fetched the same binary through undici and timed out, so the installer is used
   and pinned.
2. **Corepack needs warming before the gate.** `test_lock_wait.py` shells out to
   `pnpm exec tsx` under a 20-second budget, and the first corepack download in a
   fresh image exceeded it (`TimeoutExpired` on the `release` case). The setup runs
   the same invocation once from the same working directory, because that directory
   decides which pnpm version corepack resolves, so the test measures the wait it
   is about rather than a download.

## Reproduce

```bash
sh packages/skill-router/tests/skill_router_docker.sh          # pins Pi 1.3.0
PI_VERSION=1.4.0 sh packages/skill-router/tests/skill_router_docker.sh
```

The script prints `SKILL_ROUTER_DOCKER_OK <receipt-dir>` and leaves the receipt
directory (verification log, pack logs, Pi and Bun versions, `pi list`, and a JSON
report with the collection, the loaded packages and the tarball hashes).