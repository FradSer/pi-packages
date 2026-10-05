/**
 * Pi built-ins available to a bare Agent; extension aliases are not inherited.
 *
 * This duplicates Pi's own canonical set (`ToolName` / `allToolNames` in
 * `dist/core/tools/index.js`), and it has to: Pi's exports map publishes only
 * `.`, `./rpc-entry`, `./client` and `./experimental/plugin`, so the authoritative
 * set is not importable at runtime. The duplicate is what makes a spawn refuse an
 * id the child's own `--tools` allowlist would silently drop, so drift fails in
 * the direction that costs the most: Pi adding a built-in would make this list
 * refuse a legitimate request.
 *
 * `tests/test_agent_tool_universe.py` compares this list with the Pi the repo
 * pins for development, which is the only place the drift can be caught before a
 * caller pays for it. Record the gap upstream rather than widening this file into
 * a registry: `AGENT_BUILTIN_TOOLS` is a copy of Pi's vocabulary, not a second
 * source of truth for it.
 */
export const AGENT_BUILTIN_TOOLS: readonly string[] = [
  "read", "bash", "edit", "write", "grep", "find", "ls", "powershell",
];