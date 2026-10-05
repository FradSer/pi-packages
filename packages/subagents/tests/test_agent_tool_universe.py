"""The grantable built-in tool universe is Pi's own set, not a remembered copy.

`AGENT_BUILTIN_TOOLS` decides which ids a spawn refuses before a name is claimed.
A remembered list drifts the moment Pi adds or renames a built-in, and the drift
fails in the worse direction: a legitimate id would be refused. Pi's own
`allToolNames` is authoritative but unreachable — its exports map exposes no
tools subpath — so the installed module is read by absolute path, which is
available to a test and not to shipped code.
"""
from __future__ import annotations

import json

from subagents_helpers import REPO, SRC, run_node

FIND_PI_TOOLS = """
    import { existsSync } from "node:fs";
    import * as path from "node:path";
    const findInstalled = () => {
      // From the repository root, because that is the Pi the repo pins as a
      // devDependency and the version its checks run against. A nested copy
      // exists under a package when its `*` peer still resolves to an older
      // release, and comparing against that stale copy would fail for the wrong
      // reason: a version skew rather than a drift in this list.
      let dir = process.env.PI_REPO_ROOT ?? process.cwd();
      for (;;) {
        const candidate = path.join(dir, "node_modules", "@earendil-works", "pi-coding-agent", "dist", "core", "tools", "index.js");
        if (existsSync(candidate)) return candidate;
        const parent = path.dirname(dir);
        if (parent === dir) return "";
        dir = parent;
      }
    };
"""


def test_the_grantable_universe_matches_pis_canonical_builtin_set() -> None:
    result = run_node(f"""
      import {{ pathToFileURL }} from "node:url";
      import {{ AGENT_BUILTIN_TOOLS }} from {json.dumps((SRC / "agent-tools.ts").as_uri())};
      {FIND_PI_TOOLS}
      const file = findInstalled();
      if (!file) throw new Error("The installed pi-coding-agent tools module was not found.");
      const {{ allToolNames }} = await import(pathToFileURL(file).href);
      console.log(JSON.stringify({{ file, own: [...AGENT_BUILTIN_TOOLS].sort(), canonical: [...allToolNames].sort() }}));
    """, env_overrides={"PI_REPO_ROOT": str(REPO)})
    assert result["canonical"], "Pi reported no canonical built-in tools"
    assert result["own"] == result["canonical"]


def test_the_universe_is_what_the_refusal_message_advertises() -> None:
    """The refusal message names this list, so a universe that drifts from the
    advertised vocabulary is a spawn refused for an id the caller could only
    learn about by being refused. The `tools` parameter no longer enumerates the
    vocabulary, so the message is the one published copy a caller reads."""
    result = run_node(f"""
      import {{ AGENT_BUILTIN_TOOLS }} from {json.dumps((SRC / "agent-tools.ts").as_uri())};
      import {{ unknownAgentTools, unknownAgentToolsError }} from {json.dumps((SRC / "spawner.ts").as_uri())};
      const advertised = unknownAgentToolsError(["example"], []);
      console.log(JSON.stringify({{
        universe: [...AGENT_BUILTIN_TOOLS],
        unadvertised: AGENT_BUILTIN_TOOLS.filter((tool) => !advertised.includes(tool)),
        refused: unknownAgentTools(["example", ...AGENT_BUILTIN_TOOLS], []),
      }}));
    """)
    assert result["unadvertised"] == []
    assert result["refused"] == ["example"], result["refused"]