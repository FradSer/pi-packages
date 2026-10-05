---
"pi-matt-pocock": patch
---

The package configuration now lives at `matt-pocock.json` in Pi's agent directory, resolved through Pi's own agent-dir lookup.

The file was read from a hardcoded `~/.pi/agent/pi-matt-pocock.json`, so it ignored `PI_CODING_AGENT_DIR` and used a `pi-` prefix that no other Pi package follows. `defaultConfigFile()` now returns `join(getAgentDir(), "matt-pocock.json")`, matching how `vision.json`, `recap.json`, and `plan-mode.json` are located.

**@pi-matt-pocock**

- `matt_pocock_ask` reads `matt-pocock.json` from the agent directory: `~/.pi/agent/matt-pocock.json` by default, and `$PI_CODING_AGENT_DIR/matt-pocock.json` when that variable is set (tilde-expanded, as Pi does everywhere else).

Renaming the file is a one-line action for anyone who opted in to native dialogs:

```bash
mv ~/.pi/agent/pi-matt-pocock.json ~/.pi/agent/matt-pocock.json
```

The `PI_MATT_POCOCK_CONFIG_FILE` override is unchanged and still takes precedence.