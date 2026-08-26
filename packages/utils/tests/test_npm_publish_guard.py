import json
import subprocess
import unittest
from pathlib import Path

UTILS_PKG_DIR = Path(__file__).resolve().parents[1]
REPO = UTILS_PKG_DIR.parents[1]
GUARD_EXTENSION = UTILS_PKG_DIR / "extensions" / "npm-publish-guard.ts"


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
            "pnpm --filter web publish",
            "pnpm --filter=web publish",
            "pnpm -F api publish",
            "yarn workspace web publish",
            "pnpm --filter web --filter api -r publish",
        ):
            self.assertBlocked(command, "Package publish")

    def test_dry_run_allowance_is_per_invocation(self) -> None:
        self.assertAllowed("pnpm publish --dry-run")
        self.assertBlocked("pnpm publish --dry-run && pnpm -F api publish", "Package publish")
        self.assertBlocked("pnpm -F api publish; npm publish --dry-run", "Package publish")

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
