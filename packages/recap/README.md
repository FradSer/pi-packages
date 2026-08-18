# @fradser/pi-recap

Session recap for Pi — displays a concise, scannable summary of the current session above the TUI input box, inspired by Claude Code's `✦ Recap:` feature.

## Install

```bash
pi install npm:@fradser/pi-recap
```

## Features

- **TUI Above-Editor Display**: Once installed, the extension automatically displays the most recent recap in the widget above the editor (`✦ Recap: <summary>`).
- **Management Menu (`/recap`)**: Running `/recap` opens an interactive management TUI (similar to `@packages/memory/` and `@packages/vision/`) allowing you to generate recaps on demand, choose dedicated models, or toggle display settings.
- **Model Selection**: Supports selecting any model available in Pi's model registry (e.g. `anthropic/claude-3-5-haiku`, `openai/gpt-4o-mini`, or session default).
- **Non-blocking & In-process**: Recaps are generated asynchronously using Pi's model registry after each completed turn without spawning external child processes. Requests are deduplicated, superseded requests are cancelled, and generation has a 30-second timeout.
- **Context Continuity & Persistence**: Progressively evolves the recap by combining the previous recap with the latest turn's exchange. Recaps are persisted directly into the session branch via custom session entries (`pi.appendEntry`), restoring immediately on restarts without redundant LLM calls. Output is limited to one line and 120 characters; unchanged recaps are not persisted again.
- **Cross-Session Sync**: Automatically updates the directory session registry (`~/.pi/agent/directory-sessions/`), keeping parallel sessions informed.

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

Persisted in `~/.pi/agent/recap.json`:

```json
{
  "provider": "anthropic",
  "model": "claude-3-5-haiku",
  "enabled": true,
  "autoRecap": true
}
```

Environment variable overrides (take precedence over saved configuration):
- `PI_RECAP_MODEL` — e.g. `anthropic/claude-3-5-haiku`
- `PI_RECAP_PROVIDER` — fallback provider name
- `PI_RECAP_LANGUAGE` — e.g. `en`, `zh`, or `Japanese`

## License

MIT
