import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run_script(name, cwd, *args, home=None):
    env = dict(os.environ)
    if home:
        env["HOME"] = str(home)
    return subprocess.run(["node", str(ROOT / "scripts" / name), *args], cwd=cwd,
                          env=env, text=True, capture_output=True, timeout=15)


def test_context_target_and_isolation(tmp_path):
    project = tmp_path / "target with spaces"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    empty = run_script("context.mjs", project, home=home)
    assert empty.returncode == 0, empty.stderr
    assert "NO_PRODUCT_MD" in empty.stdout
    assert not list(home.iterdir())
    for forbidden in ["UPDATE_AVAILABLE", "SUBAGENT", "build-phase", "reference/init.md", "npx"]:
        assert forbidden not in empty.stdout
    (project / "PRODUCT.md").write_text("# Product\nUnique fixture product")
    (project / "DESIGN.md").write_text("# Design\nUnique fixture design")
    result = run_script("context.mjs", project, home=home)
    assert result.returncode == 0, result.stderr
    assert "Unique fixture product" in result.stdout
    assert "Unique fixture design" in result.stdout
    assert str(project.resolve()) in result.stdout
    assert not list(home.iterdir())


def test_context_monorepo(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["apps/*"]}))
    for app in ["alpha", "beta"]:
        target = tmp_path / "apps" / app
        target.mkdir(parents=True)
        (target / "PRODUCT.md").write_text(f"# {app} product")
    result = run_script("context.mjs", tmp_path, "--target", "apps/beta")
    assert result.returncode == 0, result.stderr
    assert "# beta product" in result.stdout
    assert "# alpha product" not in result.stdout
    missing = run_script("context.mjs", tmp_path, "--target", "apps/missing")
    assert missing.returncode != 0
    assert "TARGET" in missing.stdout + missing.stderr
    selection = run_script("context.mjs", tmp_path)
    assert "TARGET_SELECTION_REQUIRED" in selection.stdout


def test_static_detector_real_findings(tmp_path):
    bad = tmp_path / "bad fixture.html"
    bad.write_text('<!doctype html><html><body><h1>Account</h1><h3>Settings</h3></body></html>')
    result = run_script("detect.mjs", tmp_path, "--json", str(bad))
    assert result.returncode == 2, result.stderr + result.stdout
    findings = json.loads(result.stdout)
    assert any(f["antipattern"] == "skipped-heading" for f in findings)
    clean = tmp_path / "clean.html"
    clean.write_text('<p>Account settings</p>')
    result = run_script("detect.mjs", tmp_path, "--json", str(clean))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_static_detector_rejects_external_capabilities(tmp_path):
    for args in [("--json",), ("--json", "https://example.com")]:
        result = run_script("detect.mjs", tmp_path, *args)
        assert result.returncode == 1
        assert "explicit local" in result.stderr


def test_native_and_advisory_limits(tmp_path):
    (tmp_path / "PRODUCT.md").write_text("# Product\n## Platform\nios\n")
    result = run_script("context.mjs", tmp_path)
    assert "NATIVE_SUPPLEMENT_UNAVAILABLE" in result.stdout
    style = tmp_path / "style.css"
    style.write_text("p { font-family: Inter; }")
    result = run_script("detect.mjs", tmp_path, "--json", str(style))
    assert result.returncode == 0, result.stderr
    findings = json.loads(result.stdout)
    assert any(f["antipattern"] == "overused-font" and f["advisory"] for f in findings)


def test_runtime_provenance():
    import hashlib
    provenance = json.loads((ROOT / "runtime-provenance.json").read_text())
    assert provenance["revision"] == "63b04e2530f5c7b41ea83c133daab24f34912456"
    destinations = {record["destination"] for record in provenance["files"]}
    assert all(str(p.relative_to(ROOT)) in destinations for p in (ROOT / "scripts").rglob("*.mjs")
               if p.name != "check-upstream-sync.mjs")
    for record in provenance["files"]:
        data = (ROOT / record["destination"]).read_bytes()
        if record["disposition"] == "retained":
            assert hashlib.sha256(data).hexdigest() == record["sha256"]
        elif record["destination"].endswith(".mjs"):
            assert b"Modified for @fradser/pi-impeccable" in data
    assert "Copyright 2025 Paul Bakaus" in (ROOT / "licenses/impeccable-Apache-2.0.txt").read_text()
    assert provenance["licenses"]["jakub"]["revision"] == "267330e1adfc66a718fb65fa6918c1f06d0a689e"


def test_low_contrast_source_evidence(tmp_path):
    target = tmp_path / "contrast.html"
    target.write_text('<!doctype html><html><body><p style="color:#aaaaaa;background-color:#ffffff;font-size:16px">Account settings details</p></body></html>')
    result = run_script("detect.mjs", tmp_path, "--json", str(target))
    assert result.returncode == 2, result.stderr + result.stdout
    findings = json.loads(result.stdout)
    contrast = next(f for f in findings if f["antipattern"] == "low-contrast")
    assert contrast["file"] == str(target)
    assert contrast["snippet"]
    assert "Static estimates" in json.loads((ROOT / "runtime-provenance.json").read_text())["detectorPolicy"]["limits"]


def test_missing_parser_dependencies_fail(tmp_path):
    import shutil
    shutil.copytree(ROOT / "scripts", tmp_path / "scripts")
    target = tmp_path / "input.html"
    target.write_text("<p>Settings</p>")
    result = subprocess.run(["node", str(tmp_path / "scripts/detect.mjs"), "--json", str(target)],
                            cwd=tmp_path, text=True, capture_output=True, timeout=15)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Reinstall" in result.stderr
    assert not result.stdout
