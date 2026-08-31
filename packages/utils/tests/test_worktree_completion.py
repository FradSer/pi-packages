import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
COMPLETION_EXTENSION = UTILS_PKG_DIR / "extensions" / "worktree-completion.ts"


def run_ts(script: str) -> object:
    result = subprocess.run(
        ["bun", "run", "-"],
        cwd=REPO,
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"TypeScript runner failed:\n{result.stderr}")
    return json.loads(result.stdout)


GIT = shutil.which("git")


def make_git_repo(path: Path) -> None:
    def git(*args: str, cwd: Path | None = None) -> None:
        subprocess.run(["git", *args], cwd=cwd or path,
                       capture_output=True, text=True, check=True)

    git("init", "-q")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    (path / "src").mkdir()
    (path / "README.md").write_text("main readme\n")
    (path / "src" / "index.ts").write_text("export {};\n")
    git("add", "-A")
    git("commit", "-qm", "init")


class WorktreeCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="pi-wtc-")).resolve()
        self.main = self.base / "main-repo"
        self.main.mkdir()
        make_git_repo(self.main)
        self.wt_b = self.base / "wt-b"
        self.wt_c = self.base / "wt-c"
        for name in ("b", "c"):
            subprocess.run(["git", "worktree", "add", f"{self.base}/wt-{name}", "-b", name],
                           cwd=self.main, capture_output=True, text=True, check=True)

    def is_foreign(self, value: str, cwd: Path) -> bool:
        script = f"""
import {{ collectWorktreeRoots, isInForeignWorktree }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(cwd))});
console.log(JSON.stringify(isInForeignWorktree({json.dumps(value)}, {json.dumps(str(cwd))}, roots)));
"""
        return bool(run_ts(script))

    def test_main_checkout_collects_linked_worktrees_as_foreign(self) -> None:
        result = run_ts(f"""
import fs from "node:fs";
import {{ collectWorktreeRoots }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.main))});
console.log(JSON.stringify({{
  currentIsMain: roots.currentRoot === fs.realpathSync({json.dumps(str(self.main))}),
  foreignCount: roots.foreignRoots.length,
}}));
""")
        self.assertTrue(result["currentIsMain"])
        self.assertEqual(2, result["foreignCount"])

    def test_worktree_sees_siblings_and_main_as_foreign(self) -> None:
        result = run_ts(f"""
import fs from "node:fs";
import {{ collectWorktreeRoots }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.wt_b))});
const foreign = new Set(roots.foreignRoots);
console.log(JSON.stringify({{
  hasMain: foreign.has(fs.realpathSync({json.dumps(str(self.main))})),
  hasSibling: foreign.has(fs.realpathSync({json.dumps(str(self.wt_c))})),
  currentSelf: roots.currentRoot === fs.realpathSync({json.dumps(str(self.wt_b))}),
}}));
""")
        self.assertTrue(result["hasMain"])
        self.assertTrue(result["hasSibling"])
        self.assertTrue(result["currentSelf"])

    def test_non_git_directory_disables_filtering(self) -> None:
        outside = Path(tempfile.mkdtemp(prefix="pi-wtc-nogit-"))
        self.assertFalse(self.is_foreign("../anything/x.ts", outside))

    def test_main_hides_sibling_worktree_paths(self) -> None:
        self.assertTrue(self.is_foreign("../wt-b/src/index.ts", self.main))
        self.assertTrue(self.is_foreign("../wt-b/", self.main))
        self.assertFalse(self.is_foreign("src/index.ts", self.main))
        self.assertFalse(self.is_foreign("README.md", self.main))

    def test_nonexistent_leaf_under_symlinked_base_is_still_foreign(self) -> None:
        # macOS /var-style symlinks: realpath fails on missing leaves, but the
        # candidate must still resolve into the canonical worktree space.
        self.assertTrue(self.is_foreign("../wt-b/dir with space/x.ts", self.main))
        self.assertTrue(self.is_foreign(str(self.wt_b / "nope" / "x.ts"), self.main))

    def test_symlinked_base_fixture_resolves_before_filtering(self) -> None:
        # Deterministic cross-platform version of the ambient-symlink case: a
        # symlinked session path must not hide foreign roots behind it.
        linked = self.base.parent / "linked"
        os.symlink(self.base, linked, target_is_directory=True)
        try:
            via_link = linked / "main-repo"
            self.assertTrue(self.is_foreign("../wt-b/nope/x.ts", via_link))
            self.assertFalse(self.is_foreign("src/index.ts", via_link))
        finally:
            os.remove(linked)

    def test_nested_pi_worktrees_path_is_foreign_from_main(self) -> None:
        subprocess.run(["git", "worktree", "add", ".pi/worktrees/foo", "-b", "foo"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        self.assertTrue(self.is_foreign(".pi/worktrees/foo/src/index.ts", self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees/foo/src/index.ts"', self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees/foo/", self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees", self.main))
        self.assertTrue(self.is_foreign(".pi/worktrees/", self.main))
        self.assertTrue(self.is_foreign("@.pi/worktrees", self.main))
        self.assertTrue(self.is_foreign("@.pi/worktrees/", self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees"', self.main))
        self.assertTrue(self.is_foreign('@".pi/worktrees/"', self.main))

    def test_read_guard_blocks_foreign_worktree_and_allows_own_files(self) -> None:
        subprocess.run(["git", "worktree", "add", ".pi/worktrees/foo", "-b", "foo"],
                       cwd=self.main, capture_output=True, text=True, check=True)
        foreign = self.main / ".pi" / "worktrees" / "foo" / "src" / "index.ts"
        own = self.main / "src" / "index.ts"
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
registerWorktreeCompletion({{ on: (event, handler) => handlers.set(event, handler) }});
const guard = handlers.get("tool_call");
const ctx = {{ cwd: {json.dumps(str(self.main))} }};
const blocked = guard({{ toolName: "read", input: {{ path: {json.dumps(str(foreign))} }} }}, ctx);
const allowed = guard({{ toolName: "read", input: {{ path: {json.dumps(str(own))} }} }}, ctx);
console.log(JSON.stringify({{ blocked, allowed: allowed ?? null }}));
"""
        result = run_ts(script)
        self.assertTrue(result["blocked"]["block"])
        self.assertIn("enter_worktree", result["blocked"]["reason"])
        self.assertIsNone(result["allowed"])

    def test_main_repo_without_linked_worktrees_still_hides_pi_worktrees(self) -> None:
        clean_repo = self.base / "clean-repo"
        clean_repo.mkdir()
        make_git_repo(clean_repo)
        (clean_repo / ".pi" / "worktrees").mkdir(parents=True)
        (clean_repo / ".pi" / "worktrees" / "stale.txt").write_text("temp")
        self.assertTrue(self.is_foreign(".pi/worktrees", clean_repo))
        self.assertTrue(self.is_foreign(".pi/worktrees/", clean_repo))
        self.assertTrue(self.is_foreign(".pi/worktrees/stale.txt", clean_repo))
        self.assertFalse(self.is_foreign(".pi/agents", clean_repo))
        self.assertFalse(self.is_foreign("src/index.ts", clean_repo))

    def test_worktree_hides_main_and_siblings(self) -> None:
        self.assertTrue(self.is_foreign("../main-repo/README.md", self.wt_b))
        self.assertTrue(self.is_foreign("../wt-c/src/index.ts", self.wt_b))
        self.assertFalse(self.is_foreign("src/index.ts", self.wt_b))

    def test_absolute_and_home_relative_candidates_resolve_before_filtering(self) -> None:
        absolute = str(self.main / "src" / "index.ts")
        self.assertTrue(self.is_foreign(absolute, self.wt_b))
        self.assertFalse(self.is_foreign("~/outside-any-repo/file.ts", self.wt_b))

    def test_filter_drops_only_foreign_items_in_order(self) -> None:
        script = f"""
import {{ collectWorktreeRoots, filterForeignWorktreeItems }} from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const roots = collectWorktreeRoots({json.dumps(str(self.main))});
const items = [
  {{ value: "src/index.ts", label: "index.ts" }},
  {{ value: ".pi/worktrees/", label: "worktrees/" }},
  {{ value: ".pi/worktrees", label: "worktrees" }},
  {{ value: "@agent-teams-status", label: "agent-teams-status", description: ".pi/worktrees/pi-artifact-and-design/.changeset/agent-teams-status-truth-and-classifier.md" }},
  {{ value: "@agent-teams/", label: "agent-teams/", description: ".pi/worktrees/pi-artifact-and-design/packages/agent-teams/" }},
  {{ value: "../wt-b/src/index.ts", label: "index.ts", description: "../wt-b/src/index.ts" }},
  {{ value: "../wt-c/", label: "wt-c/" }},
  {{ value: ".pi/agents/", label: "agents/" }},
];
console.log(JSON.stringify(filterForeignWorktreeItems(items, {json.dumps(str(self.main))}, roots)));
"""
        result = run_ts(script)
        self.assertEqual(["src/index.ts", ".pi/agents/"], [item["value"] for item in result])

    def test_nested_pi_worktree_session_filters_sibling_and_parent_worktrees_dir(self) -> None:
        wt_foo = self.main / ".pi" / "worktrees" / "foo"
        wt_bar = self.main / ".pi" / "worktrees" / "bar"
        for name in ("foo", "bar"):
            subprocess.run(["git", "worktree", "add", f".pi/worktrees/{name}", "-b", f"branch-{name}"],
                           cwd=self.main, capture_output=True, text=True, check=True)

        self.assertFalse(self.is_foreign("src/index.ts", wt_foo))
        self.assertFalse(self.is_foreign("README.md", wt_foo))
        self.assertTrue(self.is_foreign("../bar/src/index.ts", wt_foo))
        self.assertTrue(self.is_foreign("../../.pi/worktrees", wt_foo))
        self.assertTrue(self.is_foreign("../../.pi/worktrees/", wt_foo))
        self.assertTrue(self.is_foreign("../../README.md", wt_foo))

    def test_bare_repository_session_filters_linked_worktrees(self) -> None:
        source = self.base / "bare-source"
        source.mkdir()
        make_git_repo(source)
        bare = self.base / "store.git"
        subprocess.run(["git", "clone", "--bare", str(source), str(bare)],
                       capture_output=True, text=True, check=True)
        wt_w = self.base / "wt-w"
        subprocess.run(["git", "worktree", "add", str(wt_w), "-b", "w"],
                       cwd=bare, capture_output=True, text=True, check=True)

        self.assertTrue(self.is_foreign(str(wt_w / "anything.ts"), bare))
        self.assertFalse(self.is_foreign("config", bare))

    def test_extension_registration_filters_and_delegates(self) -> None:
        script = f"""
process.env.PATH = "/nonexistent-shim:" + process.env.PATH;
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
registerWorktreeCompletion({{ on: (event, handler) => handlers.set(event, handler) }});
const handler = handlers.get("session_start");
if (!handler) throw new Error("session_start handler was not registered");

let factory = null;
const ctx = {{
  cwd: {json.dumps(str(self.main))},
  ui: {{ addAutocompleteProvider: (f) => {{ factory = f; }} }},
}};
handler({{}}, ctx);
handlers.get("resources_discover")({{ cwd: ctx.cwd, reason: "startup" }}, ctx);
if (!factory) throw new Error("autocomplete provider factory was not registered");

const current = {{
  async getSuggestions() {{
    return {{
      prefix: "@x",
      items: [
        {{ value: "@README.md", label: "README.md" }},
        {{ value: "@../wt-b/src/index.ts", label: "index.ts" }},
      ],
    }};
  }},
  applyCompletion(...args) {{ return args; }},
  shouldTriggerFileCompletion() {{ return "delegated"; }},
}};
const wrapped = factory(current);
const options = {{ signal: new AbortController().signal }};
const first = await wrapped.getSuggestions(["@x"], 0, 3, options);
const second = await wrapped.getSuggestions(["@x"], 0, 3, options);
console.log(JSON.stringify({{
  firstValues: first.items.map((i) => i.value),
  secondValues: second.items.map((i) => i.value),
  applyDelegates: JSON.stringify(wrapped.applyCompletion("L", 0, 1, {{}}, "@")) === JSON.stringify(["L", 0, 1, {{}}, "@"]),
  triggerDelegates: wrapped.shouldTriggerFileCompletion([], 0, 0) === "delegated",
}}));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertEqual(["@README.md"], report["firstValues"])
        self.assertEqual(["@README.md"], report["secondValues"])
        self.assertTrue(report["applyDelegates"])
        self.assertTrue(report["triggerDelegates"])

    def test_later_at_provider_cannot_bypass_worktree_filter(self) -> None:
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
const factories = [];
const pi = {{ on: (event, handler) => handlers.set(event, handler) }};
const ctx = {{
  cwd: {json.dumps(str(self.main))},
  ui: {{ addAutocompleteProvider: (factory) => factories.push(factory) }},
}};
registerWorktreeCompletion(pi);
handlers.get("session_start")({{}}, ctx);

// A later provider such as FFF can return its own @ results without delegating.
factories.push((current) => ({{
  async getSuggestions() {{
    return {{
      prefix: "@packages/utils/",
      items: [
        {{ value: "@packages/utils/", label: "utils/", description: "packages/utils/" }},
        {{ value: "@.pi/worktrees/pi-artifact-and-design/packages/utils/", label: "utils/", description: ".pi/worktrees/pi-artifact-and-design/packages/utils/" }},
      ],
    }};
  }},
  applyCompletion: (...args) => current.applyCompletion(...args),
  shouldTriggerFileCompletion: (...args) => current.shouldTriggerFileCompletion?.(...args) ?? true,
}}));
handlers.get("resources_discover")({{ cwd: ctx.cwd, reason: "startup" }}, ctx);

let provider = {{
  async getSuggestions() {{ return null; }},
  applyCompletion(...args) {{ return args; }},
  shouldTriggerFileCompletion() {{ return true; }},
}};
for (const factory of factories) provider = factory(provider);
const result = await provider.getSuggestions([], 0, 0, {{ signal: new AbortController().signal }});
console.log(JSON.stringify(result.items.map((item) => item.value)));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\\n{result.stderr}")
        self.assertEqual(["@packages/utils/"], json.loads(result.stdout))

    def test_filtering_follows_session_replacement_cwd(self) -> None:
        script = f"""
import registerWorktreeCompletion from {json.dumps(COMPLETION_EXTENSION.as_uri())};
const handlers = new Map();
let factory = null;
const pi = {{ on: (event, handler) => handlers.set(event, handler) }};
const makeCtx = (cwd) => ({{
  cwd,
  ui: {{ addAutocompleteProvider: (f) => {{ factory = f; }} }},
}});
registerWorktreeCompletion(pi);
const mainCtx = makeCtx({json.dumps(str(self.main))});
handlers.get("session_start")({{}}, mainCtx);
handlers.get("resources_discover")({{ cwd: mainCtx.cwd, reason: "startup" }}, mainCtx);
const current = {{ async getSuggestions() {{ return {{ items: [{{ value: "../main-repo/README.md" }}, {{ value: "src/index.ts" }}] }}; }} }};
const provider = factory(current);
const before = await provider.getSuggestions([], 0, 0, {{}});
const worktreeCtx = makeCtx({json.dumps(str(self.wt_b))});
handlers.get("session_start")({{}}, worktreeCtx);
const after = await provider.getSuggestions([], 0, 0, {{}});
console.log(JSON.stringify({{
  beforeKeptMainReadme: before.items.some((item) => item.value === "../main-repo/README.md"),
  afterDropsMainReadme: !after.items.some((item) => item.value === "../main-repo/README.md"),
  afterKeepsOwnSrc: after.items.some((item) => item.value === "src/index.ts"),
}}));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        report = json.loads(result.stdout)
        self.assertTrue(report["beforeKeptMainReadme"])
        self.assertTrue(report["afterDropsMainReadme"])
        self.assertTrue(report["afterKeepsOwnSrc"])

    def test_discovery_runs_git_once_across_repeated_rounds(self) -> None:
        counter_bin = Path(tempfile.mkdtemp(prefix="pi-wtc-bin-"))
        counter = counter_bin / "count"
        counter.write_text("0\n")
        shim = counter_bin / "git"
        shim.write_text(
            "#!/bin/sh\n"
            f'echo $(($(cat "{counter}") + 1)) > "{counter}"\n'
            f'exec {json.dumps(GIT)} "$@"\n'
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)

        script = f"""
process.env.PATH = {json.dumps(str(counter_bin))} + ":" + process.env.PATH;
const mod = await import({json.dumps(COMPLETION_EXTENSION.as_uri())});
const first = mod.getWorktreeRoots({json.dumps(str(self.main))});
const second = mod.getWorktreeRoots({json.dumps(str(self.main))});
console.log(JSON.stringify({{ sameRef: first === second }}));
"""
        # Bun snapshots PATH for child-process lookup, but pi runs on Node,
        # which re-resolves per spawn — run this scenario through node.
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise AssertionError(f"Node runner failed:\n{result.stderr}")
        self.assertTrue(json.loads(result.stdout)["sameRef"])
        # One discovery = exactly two spawns (worktree list + rev-parse).
        self.assertEqual(2, int(counter.read_text()))


if __name__ == "__main__":
    unittest.main()
