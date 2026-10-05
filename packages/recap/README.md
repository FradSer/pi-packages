# @fradser/pi-recap

Session recap for Pi — displays a concise, scannable summary of the current session above the TUI input box, inspired by Claude Code's `✦ Recap:` feature.

## Structure

```
recap/
├── index.ts          — Package-root entry point, re-exports extensions/index.ts
├── extensions/
│   ├── config.ts     — Configuration read/write + environment variable overrides
│   ├── index.ts      — Pi lifecycle hooks, /recap command, widget setup
│   └── recap.ts      — Prompt building, cleanup, cost policy, model call
├── features/         — BDD contract
├── tests/            — Package E2E tests
└── README.md
```

## Install

```bash
pi install npm:@fradser/pi-recap
```

## Features

- **TUI Above-Editor Display**: Once installed, the extension automatically displays the most recent recap in the widget above the editor (`✦ Recap: <summary>`). When the first user prompt arrives, that line is replaced by an animated `Recapping...` marker while the initial progress summary is prepared, then returns with the completed turn's outcome instead of stacking a second line.
- **Management Menu (`/recap`)**: Running `/recap` opens an interactive management TUI (similar to `@packages/memory/` and `@packages/vision/`) allowing you to generate recaps on demand, choose dedicated models, or toggle display settings.
- **Model Selection**: Supports selecting any model available in Pi's model registry (e.g. `anthropic/claude-3-5-haiku`, `openai/gpt-4o-mini`, or session default). Dismissing the picker without choosing a model clears the override, so recap generation falls back to the session default.
- **Non-blocking & In-process**: Recaps are generated asynchronously using Pi's model registry. The first user prompt starts an immediate in-progress recap so the widget can tell you that work is being recapped; after the turn completes, it refreshes with the outcome. Later turns are recapped after settlement without spawning external child processes. Requests are deduplicated, superseded requests are cancelled across authentication and provider responses, and the whole request — credentials included — is bounded by a 30-second budget that always settles, even if the provider ignores cancellation. The completion budget accommodates reasoning models before they emit recap text. Empty or generic verb-plus-identifier outputs are rejected and retried once; an uninformative retry is discarded. Before the assistant reports an outcome, the prompt treats plans and requested work as starting or planned and forbids claiming unverified actions, files, connections, or results.
- **Context Continuity & Persistence**: Progressively evolves the recap by combining the previous recap with the latest complete assistant answer and its preceding user request. Interrupted, failed, and incomplete answers are excluded; a newer complete answer for the same request replaces an older one. Recaps are persisted directly into the session branch via custom session entries (`pi.appendEntry`), restoring immediately on restarts without redundant LLM calls. Output is limited to one line and 120 characters; unchanged recaps are not persisted again.
- **Cross-Session Sync**: Automatically updates the directory session registry using pi-kit's canonical hashed directory identity and shared path resolver, so a sandboxed `PI_CODING_AGENT_DIR` is honoured instead of silently writing to the real home registry. Registry reads and updates verify the stored `cwd` before using a record; older directory names are not migrated. The recap field is the only one this package writes — `updatedAt` belongs to the session-activity writers, whose recency and liveness views it would otherwise skew.

## Automatic recap cost

Recapping on every settled turn spends a model call each time, and a reasoning model spends its thinking budget before any summary text exists. So when you have not stored an `autoRecap` preference, automatic recapping is **off for the session's own reasoning model** until you opt in:

- `/recap auto` turns it on (and stores that choice explicitly), or off again.
- Choosing a recap model (`/recap model`, the picker, or `PI_RECAP_MODEL`) also enables it — you picked that model for recaps.
- The `/recap` menu and the headless summary both show the state and the reason, so a session that stops updating never does it silently.
- Manual `/recap now`, the restored recap line from a previous session, and the display itself are unaffected.

## Commands

| Command | Description |
|---|---|
| `/recap` | Open interactive recap management menu |
| `/recap now` | Generate and refresh recap immediately |
| `/recap on` | Enable recap display widget |
| `/recap off` | Disable recap display widget |
| `/recap auto` | Toggle automatic generation after turns |
| `/recap model [provider/model]` | Set model override or open model picker |

## Configuration

Persisted in `~/.pi/agent/recap.json` (or `PI_CODING_AGENT_DIR`):

```json
{
  "provider": "anthropic",
  "model": "claude-3-5-haiku",
  "enabled": true,
  "autoRecap": true,
  "language": "auto"
}
```

`autoRecap` is omitted until you choose: an absent preference is what lets the cost policy above decide.

Environment variable overrides (take precedence over saved configuration):
- `PI_RECAP_MODEL` — e.g. `anthropic/claude-3-5-haiku`
- `PI_RECAP_PROVIDER` — fallback provider name
- `PI_RECAP_LANGUAGE` — e.g. `en`, `zh`, or `Japanese`

## License

MIT
