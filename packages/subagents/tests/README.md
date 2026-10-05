# Subagent tests

Keep scenarios beside their assertions. Share preparation and transport code in
support modules; never import a `test_*` module from another test.

- `subagents_helpers.py`: source paths, inline Node execution and isolated HOME.
- `resident_support.py`: the shared standalone child/callback setup.
- `identity_support.py`: disk identity and migration preparation.
- `native_support.py`: local HTTP servers, PTY driving and the native Pi fixture.
- `test_intent_tui.py`: intent rows, expansion, diagnostics and historical labels.

Protocol scenarios run against the real native Pi print/RPC path. TUI scenarios
cover actual keys, resize, lifecycle visibility and error rendering. Do not cross
every protocol variation with every interface when the interface adds no unique
assertion. Keep all distinct ownership, storage, parsing and recovery cases.

Native tests use temporary homes and loopback providers. Each scenario owns its
release gates and assertions; the support module only starts, waits and cleans up
transport resources. It never generates a success marker or sends `/quit` on the
scenario's behalf.

Run the whole package:

```sh
python3 -m pytest packages/subagents/tests/ -q
```

For a focused iteration, pass the relevant test modules explicitly, then run the
whole package and `pnpm typecheck` before completion. Historical verification
reports and candidate hashes in this directory record earlier runs; they are not
the current test inventory.
