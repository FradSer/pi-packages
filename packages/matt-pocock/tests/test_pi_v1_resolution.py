"""Check package-local resolution rather than only the root Pi installation."""
from __future__ import annotations

import json
import subprocess
import textwrap

from matt_pocock_helpers import PACKAGE, REPO


def test_package_resolves_pi_v1_without_narrowing_published_peers() -> None:
    script = '''
        import { fileURLToPath } from "node:url";
        import { dirname, join } from "node:path";
        import { readFileSync, existsSync } from "node:fs";
        const parentUrl = new URL("./packages/matt-pocock/package.json", import.meta.url).href;
        const names = ["pi-coding-agent", "pi-ai", "pi-tui"].map(name => `@earendil-works/${name}`);
        console.log(JSON.stringify(Object.fromEntries(names.map(name => {
          let directory = dirname(fileURLToPath(import.meta.resolve(name, parentUrl)));
          while (true) {
            const file = join(directory, "package.json");
            if (existsSync(file)) {
              const manifest = JSON.parse(readFileSync(file, "utf8"));
              if (manifest.name === name) return [name, manifest.version];
            }
            const parent = dirname(directory);
            if (parent === directory) throw new Error(`No manifest for ${name}`);
            directory = parent;
          }
        }))));
    '''
    process = subprocess.run(
        ["node", "--experimental-import-meta-resolve", "--input-type=module"],
        input=textwrap.dedent(script), cwd=REPO, text=True, capture_output=True, timeout=30,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(process.stdout)
    # The root development requirement is the cohort of record; this asserts package-local
    # resolution matches it rather than pinning the version a fourth time.
    expected = json.loads((REPO / "package.json").read_text())["devDependencies"]["@earendil-works/pi-coding-agent"].lstrip("^")
    assert set(result.values()) == {expected}, result
    manifest = json.loads((PACKAGE / "package.json").read_text())
    for name in result:
        assert name not in manifest.get("dependencies", {})
    for name in ("@earendil-works/pi-coding-agent", "@earendil-works/pi-tui"):
        assert manifest["peerDependencies"][name] == "*"


def test_live_fixtures_use_valid_pi_v1_api_signatures() -> None:
    # Recursive: the real-Pi harnesses and their fixtures live in tests/live/.
    fixtures = sorted((PACKAGE / "tests").rglob("*.ts"))
    assert fixtures
    process = subprocess.run(
        ["pnpm", "exec", "tsc", "--noEmit", "--strict", "--skipLibCheck",
         "--target", "ES2022", "--module", "ESNext", "--moduleResolution", "bundler",
         "--allowImportingTsExtensions", "--types", "node", *map(str, fixtures)],
        cwd=REPO, text=True, capture_output=True, timeout=60,
    )
    assert process.returncode == 0, process.stdout + process.stderr
