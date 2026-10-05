"""Native package resolution, not just lockfile text, names the verification cohort."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHAIN = ("kit", "subagents", "tasks", "agent-teams")
CORE = ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui")
EXPECTED_PI_VERSION = "1.0.0"


def test_split_packages_resolve_root_development_core() -> None:
    script = """
      import fs from "node:fs";
      import path from "node:path";
      import { fileURLToPath, pathToFileURL } from "node:url";
      const version = (from, name) => {
        const resolved = import.meta.resolve(name, pathToFileURL(path.join(from, "package.json")).href);
        let dir = path.dirname(fileURLToPath(resolved));
        while (true) {
          const file = path.join(dir, "package.json");
          if (fs.existsSync(file)) {
            const manifest = JSON.parse(fs.readFileSync(file, "utf8"));
            if (manifest.name === name) return manifest.version;
          }
          const parent = path.dirname(dir);
          if (parent === dir) throw new Error(`No manifest for ${name}`);
          dir = parent;
        }
      };
      const chain = %s, core = %s;
      const root = process.cwd();
      console.log(JSON.stringify(core.map(name => ({name, root: version(root, name),
        packages: Object.fromEntries(chain.map(p => [p, version(path.join(root, "packages", p), name)]))}))));
    """ % (json.dumps(CHAIN), json.dumps(CORE))
    result = subprocess.run(["node", "--experimental-import-meta-resolve", "--input-type=module", "--eval", script],
        cwd=REPO, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    for record in json.loads(result.stdout):
        assert record["root"] == EXPECTED_PI_VERSION, record
        assert set(record["packages"].values()) == {EXPECTED_PI_VERSION}, record


def test_development_core_does_not_change_published_peer_contracts() -> None:
    for package in CHAIN:
        manifest = json.loads((REPO / "packages" / package / "package.json").read_text())
        for core in CORE:
            assert manifest["peerDependencies"][core] == "*"
            assert core not in manifest.get("dependencies", {})
            assert manifest.get("devDependencies", {}).get(core) == f"^{EXPECTED_PI_VERSION}", (package, core)
    root = json.loads((REPO / "package.json").read_text())
    for core in (*CORE, "@earendil-works/pi-ai"):
        assert root["devDependencies"][core] == f"^{EXPECTED_PI_VERSION}", core
