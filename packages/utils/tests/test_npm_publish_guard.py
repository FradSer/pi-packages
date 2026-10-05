import json
import subprocess
import tempfile
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
GUARD_EXTENSION = UTILS_PKG_DIR / "extensions" / "npm-publish-guard.ts"


def workspace_probe(cwd: Path) -> bool:
    """Call the extension's pnpm-workspace detection for `cwd`."""
    script = f"""
import {{ isPnpmWorkspace }} from {json.dumps(GUARD_EXTENSION.as_uri())};
console.log(JSON.stringify(isPnpmWorkspace({json.dumps(str(cwd))})));
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
    return json.loads(result.stdout)


def blocked_label(command: str) -> str | None:
    script = f"""
import {{ matchBlockedNpmCommand }} from {json.dumps(GUARD_EXTENSION.as_uri())};
console.log(JSON.stringify(matchBlockedNpmCommand({json.dumps(command)})));
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
    return report["label"] if report else None


class NpmPublishGuardTests(unittest.TestCase):
    def assertBlocked(self, command: str, label: str) -> None:
        self.assertEqual(label, blocked_label(command))

    def assertAllowed(self, command: str) -> None:
        self.assertIsNone(blocked_label(command))

    def test_publish_blocked_across_managers(self) -> None:
        for command in ("npm publish", "pnpm publish", "yarn publish", "bun publish"):
            self.assertBlocked(command, "Package publish")

    def test_recursive_and_filtered_publishes_blocked(self) -> None:
        for command in (
            "pnpm -r publish",
            "pnpm --recursive publish",
            "pnpm recursive publish",
            "pnpm --filter web publish",
            "pnpm --filter=web publish",
            "pnpm -F api publish",
            "yarn workspace web publish",
            "pnpm --filter web --filter api -r publish",
        ):
            self.assertBlocked(command, "Package publish")

    def test_dry_run_allowance_is_per_invocation(self) -> None:
        self.assertAllowed("pnpm publish --dry-run")
        self.assertAllowed("pnpm -F api publish --dry-run")
        self.assertBlocked("pnpm publish --dry-run && pnpm -F api publish", "Package publish")
        self.assertBlocked("pnpm -F api publish; npm publish --dry-run", "Package publish")

    def test_dry_run_allowance_resists_injection_vectors(self) -> None:
        # Env values, trailing comments, and falsy spellings must not exempt a
        # real publish.
        self.assertBlocked("FOO=--dry-run npm publish", "Package publish")
        self.assertBlocked("pnpm -F api publish # --dry-run", "Package publish")
        self.assertBlocked("pnpm -F api publish --dry-run=false", "Package publish")
        self.assertBlocked('pnpm -F api publish --tag next # note: --dry-run', "Package publish")

    def test_credential_and_token_flows_blocked_without_exemptions(self) -> None:
        for command in ("npm login", "npm adduser", "npm logout"):
            self.assertBlocked(command, "npm credential flow")
        for command in ("npm token create", "npm token revoke", "npm token delete",
                        "npm token revoke --dry-run"):
            self.assertBlocked(command, "npm token mutation")

    def test_env_prefixed_invocations_blocked(self) -> None:
        self.assertBlocked(
            "NPM_CONFIG_REGISTRY=https://registry.npmjs.org npm publish",
            "Package publish",
        )

    def test_command_position_anchoring_avoids_false_positives(self) -> None:
        self.assertAllowed("echo npm login")
        self.assertAllowed("cat pnpm-publish-notes.txt")
        self.assertAllowed('git commit -m "npm publish"')

    def block_reason(self, command: str, uses_pnpm: bool) -> str:
        script = f"""
import {{ buildBlockReason }} from {json.dumps(GUARD_EXTENSION.as_uri())};
console.log(JSON.stringify(buildBlockReason("Package publish", {json.dumps(command)}, {json.dumps(uses_pnpm)})));
"""
        result = subprocess.run(
            ["node", "--input-type=module"],
            cwd=REPO,
            input=script,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_block_reason_redirects_npm_publish_in_a_pnpm_workspace(self) -> None:
        reason = self.block_reason("npm publish --access public", True)
        self.assertIn("pnpm publish --access public", reason)
        self.assertNotIn("    npm publish", reason)
        self.assertIn("workspace:*", reason)
        self.assertIn("EUNSUPPORTEDPROTOCOL", reason)

    def test_block_reason_leaves_the_command_alone_outside_a_pnpm_workspace(self) -> None:
        # Advice must match the repository: without a pnpm lockfile the command
        # is reported unchanged, with a conditional warning instead.
        reason = self.block_reason("npm publish --access public", False)
        self.assertIn("    npm publish --access public", reason)
        self.assertNotIn("This repository is a pnpm workspace", reason)
        self.assertIn("If this repository declares", reason)

    def test_block_reason_names_no_project_specific_skill(self) -> None:
        reason = self.block_reason("npm publish", True)
        self.assertNotIn("skill:", reason)

    def test_pnpm_workspace_detection_follows_the_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            nested = Path(root) / "packages" / "app"
            nested.mkdir(parents=True)
            self.assertFalse(workspace_probe(nested))
            (Path(root) / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
            self.assertTrue(workspace_probe(nested))
            self.assertTrue(workspace_probe(Path(root)))

        # A repository with a different package manager is not corrected.
        with tempfile.TemporaryDirectory() as other_root:
            nested = Path(other_root) / "packages" / "app"
            nested.mkdir(parents=True)
            (Path(other_root) / "yarn.lock").write_text("", encoding="utf-8")
            self.assertFalse(workspace_probe(nested))
