from __future__ import annotations

import json
import io
from pathlib import Path
import subprocess
import tempfile
import tarfile
import textwrap


REPO = Path(__file__).resolve().parents[1]
SCRIPT = (REPO / "scripts" / "publish-release.mjs").read_text(encoding="utf-8")


def run_node(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", "--input-type=module", "-e", textwrap.dedent(source)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_publish_script_only_enables_provenance_in_github_actions() -> None:
    assert 'process.env.GITHUB_ACTIONS === "true"' in SCRIPT
    assert '...(useProvenance ? ["--provenance"] : [])' in SCRIPT


def test_release_script_queries_the_exact_local_version() -> None:
    assert '`${name}@${version}`' in SCRIPT
    assert '"version", "--json"' in SCRIPT
    assert 'published !== JSON.stringify(local.version)' not in SCRIPT


def test_release_script_does_not_treat_every_registry_error_as_absence() -> None:
    assert "E404" in SCRIPT
    assert "isRegistryNotFound" in SCRIPT
    assert 'catch {\n    published = ""' not in SCRIPT


def test_release_module_is_importable_without_running_release() -> None:
    assert "export function publishRelease" in SCRIPT
    assert "isMainModule" in SCRIPT
    assert "await publishRelease" in SCRIPT

    result = run_node(
        """
        const module = await import("./scripts/publish-release.mjs");
        console.log(typeof module.publishRelease);
        """,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "function"


def test_registry_query_distinguishes_exact_404_from_auth_and_bad_versions() -> None:
    result = run_node(
        """
        import { queryExactVersion } from "./scripts/publish-release.mjs";
        const calls = [];
        const run = (_file, args) => {
          calls.push(args);
          if (args[1] === "@scope/pkg@1.2.3") return JSON.stringify("1.2.3");
          if (args[1] === "@scope/pkg@1.2.4") {
            const error = new Error("not found");
            error.stderr = "npm error code E404\\n";
            throw error;
          }
          if (args[1] === "@scope/pkg@1.2.9") {
            const error = new Error("not found");
            error.stdout = JSON.stringify({ error: { code: "E404" } });
            throw error;
          }
          if (args[1] === "@scope/pkg@1.2.5") {
            const error = new Error("auth");
            error.stderr = "npm error code E401\\n";
            throw error;
          }
          if (args[1] === "@scope/pi-e404@1.2.6") {
            const error = new Error("auth");
            error.stderr = "npm error code E401\\nnpm error 404 https://registry/npm/@scope/pi-e404\\n";
            throw error;
          }
          return JSON.stringify("1.2.7");
        };
        const absentVersion = queryExactVersion("@scope/pkg", "1.2.4", run);
        const jsonAbsentVersion = queryExactVersion("@scope/pkg", "1.2.9", run);
        const values = {
          present: queryExactVersion("@scope/pkg", "1.2.3", run),
          absent: absentVersion ?? null,
          jsonAbsent: jsonAbsentVersion ?? null,
        };
        for (const version of ["1.2.5", "1.2.6", "1.2.8"]) {
          try { queryExactVersion(version === "1.2.6" ? "@scope/pi-e404" : "@scope/pkg", version, run); }
          catch (error) { values[version] = error.message; }
        }
        values.calls = calls;
        console.log(JSON.stringify(values));
        """,
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["present"] == "1.2.3"
    assert values["absent"] is None
    assert values["jsonAbsent"] is None
    assert "release stopped" in values["1.2.5"]
    assert "release stopped" in values["1.2.6"]
    assert "release stopped" in values["1.2.8"]
    assert "@scope/pkg@1.2.3" in [call[1] for call in values["calls"]]


def test_release_selection_is_stubbed_and_keeps_kit_first() -> None:
    result = run_node(
        """
        import { publishRelease } from "./scripts/publish-release.mjs";
        const workspacePackages = new Map([
          ["@fradser/pi-kit", { directory: "kit", version: "1.0.0" }],
          ["pi-b", { directory: "b", version: "2.0.0" }],
        ]);
        const queries = [];
        const publishes = [];
        const result = publishRelease({
          rootDir: "/tmp/release-root",
          packagesDir: "/tmp/release-root/packages",
          workspacePackages,
          publishScope: ["@fradser/pi-kit", "pi-b"],
          queryVersion(name, version) { queries.push(`${name}@${version}`); return undefined; },
          verifyPackedManifest() {},
          execFileSync(file, args, options) { publishes.push([file, args, options]); },
          useProvenance: false,
          logger: { log() {} },
        });
        console.log(JSON.stringify({ queries, publishes, published: result.published.map(({ name }) => name) }));
        """,
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["queries"] == ["@fradser/pi-kit@1.0.0", "pi-b@2.0.0"]
    assert [call[0] for call in values["publishes"]] == ["pnpm", "pnpm"]
    assert all(call[1][0:2] == ["publish", "--filter"] for call in values["publishes"])
    assert all(call[2]["cwd"] == "/tmp/release-root" for call in values["publishes"])
    assert values["published"] == ["@fradser/pi-kit", "pi-b"]


def test_pack_check_mode_covers_workspace_packages_without_registry_or_publish() -> None:
    result = run_node(
        """
        import { publishRelease } from "./scripts/publish-release.mjs";
        const workspacePackages = new Map([
          ["@fradser/pi-kit", { directory: "kit", version: "1.0.0" }],
          ["pi-b", { directory: "b", version: "2.0.0" }],
          ["pi-extra", { directory: "extra", version: "3.0.0" }],
        ]);
        const verified = [];
        const checked = publishRelease({
          workspacePackages,
          publishScope: ["@fradser/pi-kit", "pi-b"],
          verifyPackedManifest(directory) { verified.push(directory); },
          execFileSync() { throw new Error("registry or publish must not run in check mode"); },
          checkOnly: true,
          logger: { log() {} },
        });
        console.log(JSON.stringify({ names: checked.checked.map(({ name }) => name), verified }));
        """,
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values["names"] == ["@fradser/pi-kit", "pi-b", "pi-extra"]
    assert values["verified"] == [
        str(REPO / "packages" / "kit"),
        str(REPO / "packages" / "b"),
        str(REPO / "packages" / "extra"),
    ]


def test_packed_manifest_failure_uses_real_tar_format_without_publish(tmp_path: Path) -> None:
    tarball = tmp_path / "package.tgz"
    manifest = {"name": "demo", "version": "1.0.0", "dependencies": {"kit": "workspace:*"}}
    with tarfile.open(tarball, "w:gz") as archive:
        payload = json.dumps(manifest).encode("utf-8")
        info = tarfile.TarInfo("package/package.json")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    result = run_node(
        f"""
        import {{ execFileSync as realExecFileSync }} from "node:child_process";
        import {{ verifyPackedManifest }} from "./scripts/publish-release.mjs";
        try {{
          verifyPackedManifest("packages/kit", {{
            execFileSync(file, args, options) {{
              if (file === "pnpm") return JSON.stringify({{ filename: {json.dumps(str(tarball))} }});
              return realExecFileSync(file, args, options);
            }},
          }});
          console.log("unexpected-pass");
        }} catch (error) {{
          console.log(error.message);
        }}
        """,
    )
    assert result.returncode == 0, result.stderr
    assert "unresolved workspace protocol dependency" in result.stdout


def test_pack_validation_mode_is_registry_free_and_kit_first() -> None:
    feature = (REPO / "features" / "publish-provenance.feature").read_text(encoding="utf-8")
    assert "Pack validation can run without registry access" in feature
    assert '"@fradser/pi-kit"' in SCRIPT
    assert 'process.argv.includes("--check")' in SCRIPT


def test_workflow_runs_publish_script_after_version_commits() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "publish: node scripts/publish-release.mjs" in workflow
    assert "NPM_CONFIG_PROVENANCE" in workflow
    assert "oven-sh/setup-bun@v2" in workflow
    assert 'bun-version: "1.4.1"' in workflow
    assert "actions/setup-python@v7" in workflow
    assert "python3 -m pip install" in workflow
    assert "run: pnpm check" in workflow


def test_pull_request_quality_workflow_runs_the_same_check() -> None:
    workflow = (REPO / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")
    assert "pull_request:" in workflow
    assert "oven-sh/setup-bun@v2" in workflow
    assert 'bun-version: "1.4.1"' in workflow
    assert "actions/setup-python@v7" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "python3 -m pip install" in workflow
    assert "run: pnpm check" in workflow


def test_workflow_has_a_main_branch_publish_retry() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "if: github.ref == 'refs/heads/main'" in workflow
    assert "node scripts/publish-release.mjs" in workflow


def test_workflow_skips_retry_when_changesets_created_a_version_pr() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "steps.changesets.outputs.hasChangesets != 'true'" in workflow
    assert "steps.changesets.outputs.has-changesets" not in workflow


def test_workflow_uses_node_24_compatible_actions() -> None:
    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "actions/checkout@v5" in workflow
    assert "actions/setup-node@v5" in workflow
    assert "pnpm/action-setup@v5" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-node@v4" not in workflow
    assert "pnpm/action-setup@v4" not in workflow


def test_publish_allowlist_includes_skill_router() -> None:
    assert '"pi-skill-router"' in SCRIPT
    assert '"pi-mattpocock"' not in SCRIPT
    assert '"pi-marketingskills"' not in SCRIPT


def test_publish_script_verifies_packed_manifest_before_publishing() -> None:
    feature = (REPO / "features" / "publish-provenance.feature").read_text(encoding="utf-8")
    assert "Publishing verifies packed packages contain no unresolved workspace protocols" in feature
    assert "verifyPackedManifest" in SCRIPT
    assert "workspace:" in SCRIPT


def test_installation_audit_supports_object_sources_and_sdk_path_forms() -> None:
    feature = (REPO / "features" / "package-root-entry.feature").read_text(encoding="utf-8")
    assert "Installation audit follows Pi package source forms" in feature

    import_result = run_node(
        """
        const module = await import("./scripts/check-installation.mjs");
        console.log(typeof module.checkInstallation);
        """,
    )
    assert import_result.returncode == 0, import_result.stderr
    assert import_result.stdout.strip() == "function"

    package_entries: list[object] = []
    for package_dir in sorted((REPO / "packages").iterdir()):
        manifest_path = package_dir / "package.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("pi") and "pi-package" not in manifest.get("keywords", []):
            continue
        if manifest["name"] == "@fradser/pi-utils":
            package_entries.append({"source": f"npm:{manifest['name']}@{manifest['version']}", "extensions": []})
        elif manifest["name"] == "@fradser/pi-monitor":
            package_entries.append(package_dir.as_uri())
        else:
            package_entries.append(str(package_dir))

    with tempfile.TemporaryDirectory() as temp_dir:
        settings_path = Path(temp_dir) / "settings.json"
        settings_path.write_text(
            json.dumps({"packages": package_entries, "privateValue": "do-not-print"}),
            encoding="utf-8",
        )
        result = subprocess.run(
            ["node", "scripts/check-installation.mjs", str(settings_path)],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "do-not-print" not in result.stdout


def test_installation_audit_diagnoses_entries_without_echoing_private_values(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "packages": [
                    {"secret": "also-private"},
                    {"source": str(tmp_path / "private-package"), "token": "do-not-print"},
                    None,
                ]
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["node", "scripts/check-installation.mjs", str(settings_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "DEAD     settings.packages[1]" in result.stdout
    assert "INVALID  settings.packages[0]" in result.stdout
    assert "settings.packages[1]" in result.stdout
    assert "settings.packages[2]" in result.stdout
    assert "do-not-print" not in result.stdout
    assert "also-private" not in result.stdout
    assert str(tmp_path) not in result.stdout


def test_root_quality_feature_and_scripts_are_declared() -> None:
    feature = (REPO / "features" / "repository-quality.feature").read_text(encoding="utf-8")
    assert "The check command runs all local quality gates" in feature
    assert "Pull requests and releases share the quality gate" in feature
    assert "CI installs the Bun runtime required by package tests" in feature
    assert "Local publishing uses the repository quality gate" in feature

    manifest = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    assert manifest["scripts"]["test"] == "python3 -m pytest packages tests"
    assert manifest["scripts"]["check"] == "pnpm test && pnpm typecheck && pnpm pack:check"
    assert manifest["scripts"]["typecheck"] == "pnpm exec tsc --noEmit -p tsconfig.extensions.json"
    assert manifest["scripts"]["pack:check"] == "node scripts/publish-release.mjs --check"
    assert manifest["scripts"]["publish"] == "pnpm check && node scripts/publish-release.mjs"
    for documentation in [REPO / "README.md", REPO / "README.zh-CN.md", REPO / "AGENTS.md"]:
        text = documentation.read_text(encoding="utf-8")
        assert "pytest" in text
        assert "1.4.1" in text
