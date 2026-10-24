#!/usr/bin/env python3
"""Build a byte-verified, read-only freeze of the continual-learning runtime.

The continuous-learning studies import and containerise a frozen copy of the
runtime so the checkout can keep changing underneath them. This script produces
that copy plus the two manifests a frozen study wrapper verifies:

    <dest>/frozen-source.json              inventory of the runtime and study sources
    <dest>/native-dependency-bindings.json bundled SDK and declaration parser files

Both manifests and every listed file are made read-only. The script re-verifies
the result before exiting, so a successful run is a self-checked freeze.

Usage:
    python3 packages/continual-learning/scripts/freeze-correction-study-source.py <dest>

Nothing here contacts a service, runs Docker or spends anything.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PACKAGES = ("continual-learning", "kit")
ROOT_FILES = ("AGENTS.md", "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml", "tsconfig.extensions.json")
SOURCE_SUFFIXES = {".ts", ".mts", ".js", ".mjs", ".json", ".md", ".py", ".sh", ".feature"}
SOURCE_EXCLUDES = {"node_modules", ".git", ".memory", ".pi", ".pytest_cache", "__pycache__"}
SDK_RELATIVE = Path("packages/continual-learning/node_modules/@typesafe-ai/sdk")
PARSER_RELATIVE = Path("packages/continual-learning/node_modules/@babel/parser")
NATIVE_RELATIVES = (SDK_RELATIVE, PARSER_RELATIVE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_tree(source: Path, target: Path) -> None:
    for item in sorted(source.rglob("*")):
        relative = item.relative_to(source)
        if any(part in SOURCE_EXCLUDES for part in relative.parts):
            continue
        if item.is_symlink():
            continue
        if item.is_dir():
            (target / relative).mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target / relative)


def freeze(dest: Path) -> tuple[dict[str, str], dict[str, str]]:
    for package in PACKAGES:
        root = REPO / "packages" / package
        entry = root / "index.ts"
        if not root.is_dir() or root.is_symlink() or not entry.is_file() or entry.is_symlink():
            raise SystemExit(f"missing runtime dependency: {package}")
    for relative in NATIVE_RELATIVES:
        dependency = REPO / relative
        if not dependency.is_dir() or not any(item.is_file() and not item.is_symlink() for item in dependency.rglob("*")):
            raise SystemExit("missing or empty native dependency")
        if any(item.is_symlink() for item in dependency.rglob("*")):
            raise SystemExit("symlinked native dependency entry")
    if not all((REPO / PARSER_RELATIVE / name).is_file() for name in ("package.json", "lib/index.js")):
        raise SystemExit("missing native parser dependency entry")
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"refusing to reuse a non-empty destination: {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        source = REPO / name
        if source.is_file():
            shutil.copy2(source, dest / name)
    for package in PACKAGES:
        copy_tree(REPO / "packages" / package, dest / "packages" / package)
    # Runtime dependencies excluded from the source inventory need their own
    # complete, byte-bound inventory. Never rely on an ambient transitive install.
    for relative in NATIVE_RELATIVES:
        dependency = REPO / relative
        for item in sorted(dependency.rglob("*")):
            if item.is_symlink() or not item.is_file():
                continue
            target = dest / relative / item.relative_to(dependency)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    kit = dest / "packages" / "kit"
    kit_link = dest / "packages" / "continual-learning" / "node_modules" / "@fradser" / "pi-kit"
    kit_link.parent.mkdir(parents=True, exist_ok=True)
    kit_link.symlink_to(os.path.relpath(kit, kit_link.parent), target_is_directory=True)
    kit_link.parent.chmod(0o555)
    source_files: dict[str, str] = {}
    for package in PACKAGES:
        base = dest / "packages" / package
        for item in sorted(base.rglob("*")):
            relative = item.relative_to(dest)
            if any(part in SOURCE_EXCLUDES for part in relative.parts):
                continue
            if item.is_symlink() or not item.is_file() or item.suffix not in SOURCE_SUFFIXES:
                continue
            source_files[str(relative)] = digest(item)
    for name in ROOT_FILES:
        if (dest / name).is_file():
            source_files[name] = digest(dest / name)
    native_files: dict[str, str] = {}
    for relative in NATIVE_RELATIVES:
        for item in sorted((dest / relative).rglob("*")):
            if item.is_symlink() or not item.is_file():
                continue
            native_files[str(item.relative_to(dest))] = digest(item)
    for manifest, payload in (
        (dest / "frozen-source.json", {"kind": "frozen-source", "version": 1, "files": source_files}),
        (dest / "native-dependency-bindings.json", {"kind": "native-dependency-bindings", "version": 1, "kitRoot": str(kit), "files": native_files}),
    ):
        manifest.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
        manifest.chmod(0o444)
    for relative in (*source_files, *native_files):
        (dest / relative).chmod(0o444)
    for directory in sorted({(dest / relative).parent for relative in (*source_files, *native_files)}, reverse=True):
        directory.chmod(0o555)
    dest.chmod(0o555)
    return source_files, native_files


def verify(dest: Path, source_files: dict[str, str], native_files: dict[str, str]) -> None:
    for name, expected in (( "frozen-source.json", source_files), ("native-dependency-bindings.json", native_files)):
        manifest = dest / name
        if manifest.stat().st_mode & 0o222:
            raise SystemExit(f"manifest is writable: {manifest}")
        payload = json.loads(manifest.read_text())
        if payload["files"] != expected:
            raise SystemExit(f"manifest inventory changed: {manifest}")
    native_manifest = json.loads((dest / "native-dependency-bindings.json").read_text())
    kit = dest / "packages" / "kit"
    kit_link = dest / "packages" / "continual-learning" / "node_modules" / "@fradser" / "pi-kit"
    if native_manifest.get("kitRoot") != str(kit) or not kit_link.is_symlink() or kit_link.resolve() != kit.resolve():
        raise SystemExit("frozen kit dependency changed")
    if not native_files:
        raise SystemExit("missing or symlinked native dependency")
    actual_native: set[str] = set()
    for relative in NATIVE_RELATIVES:
        dependency = dest / relative
        if not dependency.is_dir() or dependency.is_symlink():
            raise SystemExit("missing or symlinked native dependency")
        ancestor = dependency.parent
        while ancestor != dest:
            if ancestor.is_symlink():
                raise SystemExit("symlinked native dependency ancestor")
            ancestor = ancestor.parent
        for item in dependency.rglob("*"):
            if item.is_symlink():
                raise SystemExit("symlinked native dependency entry")
            if item.is_file():
                actual_native.add(str(item.relative_to(dest)))
    if actual_native != set(native_files):
        raise SystemExit("native dependency inventory changed")
    for relative in (*source_files, *native_files):
        path = dest / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise SystemExit(f"invalid frozen relative path: {relative}")
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"missing or symlinked frozen file: {relative}")
        if path.stat().st_mode & 0o222:
            raise SystemExit(f"frozen file is writable: {relative}")
        if digest(path) != source_files.get(relative, native_files.get(relative)):
            raise SystemExit(f"frozen file changed after manifest: {relative}")
        if not path.resolve().is_relative_to(dest.resolve()):
            raise SystemExit(f"frozen file escapes the freeze: {relative}")
    inventory: set[str] = set()
    for package in PACKAGES:
        for item in (dest / "packages" / package).rglob("*"):
            relative = item.relative_to(dest)
            if any(part in SOURCE_EXCLUDES for part in relative.parts):
                continue
            if item.is_symlink():
                raise SystemExit(f"unexpected frozen symlink: {relative}")
            if item.is_file() and item.suffix in SOURCE_SUFFIXES:
                inventory.add(str(relative))
    for name in (dest / "frozen-source.json", dest / "native-dependency-bindings.json"):
        inventory.discard(str(name.relative_to(dest)))
    missing = inventory - set(source_files)
    if missing:
        raise SystemExit(f"unbound frozen files: {sorted(missing)[:5]}")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    dest = Path(sys.argv[1]).resolve()
    source_files, native_files = freeze(dest)
    verify(dest, source_files, native_files)
    manifest_digest = hashlib.sha256((dest / "frozen-source.json").read_bytes()).hexdigest()
    native_digest = hashlib.sha256((dest / "native-dependency-bindings.json").read_bytes()).hexdigest()
    print(json.dumps({
        "dest": str(dest),
        "sourceFiles": len(source_files),
        "nativeFiles": len(native_files),
        "frozenSourceSha256": manifest_digest,
        "nativeBindingsSha256": native_digest,
        "verified": os.access(dest / "frozen-source.json", os.R_OK),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
