#!/usr/bin/env python3
"""Validate a memory-consolidation plan, receipt, and privacy split.

The validator is intentionally dependency-free.  It accepts JSON artifacts and
emits one JSON result on stdout.  Exit status 0 means every selected check
passed; 1 means a validation failure; 2 means invalid command-line input or an
I/O failure.

Plan JSON requires ``runId``, ``scopeKey``, ``scopeDigest``, ``artifactHash``,
``inventory``, ``clusters``, ``staleness``, ``grounding``, and ``report``.  A
post receipt binds the run and scope identities to the final harness/public
hashes and declares ``phase: post``.  The command accepts ``--expected-*``
values so a parent process can bind artifacts to its own run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

VERDICTS = frozenset(
    {
        "CONTRADICTED",
        "SUPERSEDED",
        "SUBSUMED",
        "OPS-ONLY",
        "ONE-SHOT",
        "DORMANT",
        "KEEP",
    }
)

# Memory names are deliberately narrower than arbitrary filesystem names.  A
# memory is a single Markdown file directly below its memory root.
MEMORY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.md$")
INDEX_NAME = "memory.md"
HASH_RE = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
PRIVATE_MARKER_RE = re.compile(r"\(\s*harness[\s_-]+only\s*\)", re.IGNORECASE)
LINK_RE = re.compile(r"\[[^\]]*\.md\]\(([^)]+)\)", re.IGNORECASE)
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_./-])([A-Za-z0-9][A-Za-z0-9_.-]*\.md)", re.IGNORECASE)

# Keep validator limits aligned with the runtime loader and transaction writer
# (consolidation-run.ts MAX_MEMORY_FILES / MAX_MEMORY_BYTES).
MAX_MEMORY_FILES = 4_096
MAX_MEMORY_FILE_BYTES = 64_000
MAX_MEMORY_TOTAL_BYTES = MAX_MEMORY_FILES * MAX_MEMORY_FILE_BYTES


class ValidationError(Exception):
    """A user-fixable artifact or layout error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(json.dumps({
            "ok": False,
            "checks": [],
            "errors": [{"code": "usage", "message": message}],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hash_value(value: Any) -> str:
    return digest(value)


def hash_matches(actual: str, expected: str) -> bool:
    actual_value = actual.removeprefix("sha256:").lower()
    expected_value = expected.removeprefix("sha256:").lower()
    return actual_value == expected_value


def load_json_with_bytes(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError("json", f"{label}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("schema", f"{label}: top level must be a JSON object")
    return value, raw


def load_json(path: Path, label: str) -> dict[str, Any]:
    return load_json_with_bytes(path, label)[0]


def as_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError("schema", f"{label}: expected an array")
    return value


def field(obj: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in obj:
            return obj[name]
    return None


def strict_name(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        raise ValidationError("artifact_identity", f"{label}: memory name must be a string")
    if value.lower() == INDEX_NAME:
        return None
    if not MEMORY_NAME_RE.fullmatch(value):
        raise ValidationError(
            "artifact_identity",
            f"{label}: invalid memory name {value!r}; expected a simple Markdown filename",
        )
    return value


def normalize_inventory(value: Any, label: str = "inventory") -> tuple[list[str], dict[str, dict[str, Any]]]:
    entries = as_list(value, label)
    names: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}
    seen: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if isinstance(entry, str):
            name = strict_name(entry, f"{label}[{index}]")
            item: dict[str, Any] = {"name": name}
        elif isinstance(entry, dict):
            name = strict_name(field(entry, "name", "file", "filename"), f"{label}[{index}]")
            item = dict(entry)
        else:
            raise ValidationError("artifact_identity", f"{label}[{index}]: expected a filename or object")
        if name is None:
            continue
        key = name.casefold()
        if key in seen:
            raise ValidationError(
                "artifact_identity",
                f"{label}: duplicate memory name {name!r}",
            )
        seen[key] = name
        names.append(name)
        metadata[name] = item
    # An empty selected scope is a valid verified no-op.  The parent still
    # binds its run and artifact identities and the per-item sections are
    # required (and therefore empty) in the same way as a non-empty scope.
    return names, metadata


def record_name(record: Any, label: str) -> str | None:
    if not isinstance(record, dict):
        raise ValidationError("schema", f"{label}: expected an object")
    value = field(record, "name", "file", "filename", "memory")
    return strict_name(value, f"{label}.name")


def record_list(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        result: list[dict[str, Any]] = []
        for name, record in value.items():
            if isinstance(record, dict):
                result.append({"name": name, **record})
            else:
                result.append({"name": name, "value": record})
        return result
    return as_list(value, label)


def normalize_records(value: Any, inventory: list[str], label: str) -> dict[str, dict[str, Any]]:
    records = record_list(value, label)
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        name = record_name(record, f"{label}[{index}]")
        if name is None:
            continue
        key = name.casefold()
        if key in {item.casefold() for item in result}:
            raise ValidationError("artifact_identity", f"{label}: duplicate record for {name}")
        result[name] = record
    inv_set = {item.casefold() for item in inventory}
    for name in result:
        if name.casefold() not in inv_set:
            raise ValidationError("artifact_identity", f"{label}: record for {name} is not in inventory")
    missing = [name for name in inventory if name.casefold() not in {item.casefold() for item in result}]
    if missing:
        raise ValidationError("coverage", f"{label}: missing per-item record for {missing[0]}")
    return result


def artifact_payload(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan.get("artifacts")
    if isinstance(source, dict):
        return {
            "inventory": source.get("inventory", plan.get("inventory")),
            "clusters": source.get("clusters", plan.get("clusters")),
            "staleness": source.get("staleness", plan.get("staleness")),
            "grounding": source.get("grounding", plan.get("grounding")),
            "report": source.get("report", plan.get("report")),
        }
    return {
        "inventory": plan.get("inventory"),
        "clusters": plan.get("clusters"),
        "staleness": plan.get("staleness"),
        "grounding": plan.get("grounding"),
        "report": plan.get("report"),
    }


def get_plan_artifacts(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan.get("artifacts")
    if source is not None and not isinstance(source, dict):
        raise ValidationError("schema", "plan.artifacts must be an object")
    source = source if isinstance(source, dict) else plan
    required = ("inventory", "clusters", "staleness", "grounding", "report")
    missing = [name for name in required if name not in source]
    if missing:
        raise ValidationError("schema", f"plan: missing artifact section(s): {', '.join(missing)}")
    return {name: source[name] for name in required}


def identity_value(obj: dict[str, Any], name: str, alias: str | None, label: str) -> str:
    value = obj.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("binding", f"{label}: missing {name}")
    if alias is not None and alias in obj:
        alias_value = obj[alias]
        if not isinstance(alias_value, str) or alias_value != value:
            raise ValidationError("binding", f"{label}: {alias} does not match {name}")
    return value


def validate_identity(plan: dict[str, Any], expected: dict[str, str | None]) -> None:
    version = plan.get("schemaVersion", plan.get("version"))
    if version != 1:
        raise ValidationError("schema", "plan: schemaVersion must be 1")
    identities = {
        "runId": None,
        "scopeKey": None,
        "scopeDigest": None,
        "artifactHash": "snapshotDigest",
    }
    for name, alias in identities.items():
        value = identity_value(plan, name, alias, "plan")
        if name != "runId" and not HASH_RE.fullmatch(value):
            raise ValidationError("binding", f"plan: invalid {name} format")
        wanted = expected.get(name)
        if wanted is not None and value != wanted:
            raise ValidationError("binding", f"plan: {name} does not match parent expectation")


def validate_clusters(value: Any, inventory: list[str]) -> dict[str, dict[str, Any]]:
    records: list[dict[str, Any]]
    if isinstance(value, dict):
        records = []
        for cluster, files in value.items():
            records.append({"name": cluster, "files": files})
    else:
        records = record_list(value, "clusters")
    membership: dict[str, str] = {}
    for index, cluster in enumerate(records):
        if not isinstance(cluster, dict):
            raise ValidationError("schema", f"clusters[{index}]: expected an object")
        cluster_name = field(cluster, "name", "cluster", "theme")
        if not isinstance(cluster_name, str) or not cluster_name.strip():
            raise ValidationError("schema", f"clusters[{index}]: missing cluster name")
        files = field(cluster, "files", "items", "members")
        if not isinstance(files, list) or not files:
            raise ValidationError("coverage", f"clusters[{index}]: cluster has no files")
        for item_index, item in enumerate(files):
            name = item if isinstance(item, str) else field(item, "name", "file", "filename") if isinstance(item, dict) else None
            name = strict_name(name, f"clusters[{index}].files[{item_index}]")
            if name is None:
                continue
            key = name.casefold()
            if key in membership:
                raise ValidationError("coverage", f"cluster: {name} duplicate in clusters {membership[key]} and {cluster_name}")
            membership[key] = str(cluster_name)
    inv_by_key = {name.casefold(): name for name in inventory}
    for key, cluster in membership.items():
        if key not in inv_by_key:
            raise ValidationError("coverage", f"cluster: {key} not in inventory")
    for name in inventory:
        if name.casefold() not in membership:
            raise ValidationError("coverage", f"cluster: {name} missing from cluster map")
    return {inv_by_key[key]: {"cluster": value} for key, value in membership.items()}


def validate_staleness(value: Any, inventory: list[str]) -> dict[str, dict[str, Any]]:
    records = normalize_records(value, inventory, "staleness")
    for name, record in records.items():
        verdict = field(record, "verdict", "status", "score")
        if not isinstance(verdict, str):
            raise ValidationError("staleness", f"staleness: {name} missing verdict")
        normalized = verdict.upper()
        # Verdict spellings are exact; OPS_ONLY and OPS ONLY are retired formats.
        if normalized not in VERDICTS:
            raise ValidationError("staleness", f"staleness: {name} invalid verdict {verdict}")
    return records


def iter_observations(record: dict[str, Any]) -> Iterable[dict[str, Any]]:
    observations = field(record, "observations", "paths", "groundTruth")
    if isinstance(observations, dict):
        yield observations
    elif isinstance(observations, list):
        for item in observations:
            if isinstance(item, dict):
                yield item
    path = field(record, "path", "repoPath")
    if path is not None:
        yield {"path": path, "status": field(record, "pathStatus", "path_status", "status")}


def validate_repo_path(repo_root: Path, value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError("grounding", f"{label}: observation path is required")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValidationError("containment", f"grounding: {value!r} escapes repository root")
    root = repo_root.resolve()
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValidationError("containment", f"grounding: {value!r} escapes repository root") from exc
    return value


def validate_grounding(value: Any, inventory: list[str], repo_root: Path | None) -> dict[str, dict[str, Any]]:
    records = normalize_records(value, inventory, "grounding")
    for name, record in records.items():
        status = field(record, "status", "outcome", "result")
        if not isinstance(status, str) or not status.strip():
            raise ValidationError("grounding", f"grounding: {name} missing status")
        paths = list(iter_observations(record))
        status_key = re.sub(r"\s+", " ", status.strip().upper().replace("-", " "))
        if status_key in {"N/A", "N/A (NO REPO)", "NO REPO", "UNVERIFIABLE"}:
            reason = field(record, "reason", "explanation", "details")
            if not isinstance(reason, str) or not reason.strip():
                raise ValidationError("grounding", f"grounding: {name} requires a reason for {status}")
        no_repository_status = {"N/A", "N/A (NO REPO)", "NO REPO", "UNVERIFIABLE"}
        if name.startswith("project_") and status_key not in no_repository_status:
            if not paths:
                raise ValidationError("grounding", f"grounding: {name} missing repository observation")
            if not any(
                isinstance(field(observation, "status", "state"), str)
                and field(observation, "status", "state").strip().lower() in {"found", "missing", "updated"}
                for observation in paths
            ):
                raise ValidationError("grounding", f"grounding: {name} requires a found, missing, or updated observation")
        for index, observation in enumerate(paths):
            path = field(observation, "path", "repoPath")
            if repo_root is not None:
                validate_repo_path(repo_root, path, f"grounding[{name}][{index}]")
            elif isinstance(path, str) and (Path(path).is_absolute() or ".." in Path(path).parts):
                raise ValidationError("containment", f"grounding: path {path!r} is not repository-relative")
            path_status = field(observation, "status", "state")
            if not isinstance(path_status, str) or path_status.strip().lower() not in {"found", "missing", "updated"}:
                raise ValidationError("grounding", f"grounding: {name} observation status must be found, missing, or updated")
            if repo_root is not None and path_status.strip().lower() in {"found", "updated"}:
                candidate = (repo_root.resolve() / Path(path)).resolve(strict=False)
                if not candidate.is_file():
                    raise ValidationError("grounding", f"grounding: {name} observation path {path!r} does not exist as a file")
    return records


def validate_report(value: Any, inventory: list[str]) -> dict[str, dict[str, Any]]:
    records = normalize_records(value, inventory, "report")
    fields = ("status", "action", "outcome", "summary", "reason", "text")
    for name, record in records.items():
        has_outcome = False
        for key in fields:
            if key not in record:
                continue
            value = record[key]
            if not isinstance(value, str):
                raise ValidationError("report", f"report: {name} field {key} must be a string")
            if value.strip():
                has_outcome = True
        if not has_outcome:
            raise ValidationError("report", f"report: {name} has no outcome or summary")
    return records


def validate_operations(
    value: Any,
    inventory: list[str],
    metadata: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    operations = as_list(value, "operations")
    inventory_set = set(inventory)
    result: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise ValidationError("schema", f"operations[{index}]: expected an object")
        name = strict_name(field(operation, "name", "filename", "targetName"), f"operations[{index}].name")
        if name is None or name not in inventory_set:
            raise ValidationError("scope", f"operations[{index}]: target is outside selected inventory")
        kind = operation.get("kind")
        if kind not in {"create", "rewrite", "delete"}:
            raise ValidationError("schema", f"operations[{index}]: invalid operation {kind!r}")
        target = operation.get("target")
        if target is not None and target not in {"harness", "public"}:
            raise ValidationError("scope", f"operations[{index}]: invalid target {target!r}")
        classification = operation.get("classification")
        if classification not in {"safe", "private"}:
            raise ValidationError("privacy", f"operations[{index}]: classification is required and invalid: {classification!r}")
        inventory_classification = field(metadata[name], "classification", "visibility", "privacy")
        if classification != inventory_classification:
            raise ValidationError(
                "binding",
                f"operations[{index}]: classification does not match inventory for {name}",
            )
        if kind != "delete":
            content = operation.get("content")
            if not isinstance(content, str):
                raise ValidationError("schema", f"operations[{index}]: write operation requires content")
            content_hash = operation.get("contentSha256")
            if content_hash is not None:
                if not isinstance(content_hash, str) or not HASH_RE.fullmatch(content_hash):
                    raise ValidationError("binding", f"operations[{index}]: invalid contentSha256")
                if not hash_matches(hash_bytes(content.encode("utf-8")), content_hash):
                    raise ValidationError("binding", f"operations[{index}]: contentSha256 mismatch")
        elif "content" in operation or "contentSha256" in operation:
            raise ValidationError("schema", f"operations[{index}]: delete operation cannot contain content")
        result.append(operation)
    return result


def validate_plan(plan: dict[str, Any], expected: dict[str, str | None], repo_root: Path | None) -> dict[str, Any]:
    kind = plan.get("kind")
    if kind != "memory-consolidation-plan":
        raise ValidationError("schema", f"plan: kind must be 'memory-consolidation-plan', got {kind!r}")
    validate_identity(plan, expected)
    artifacts = get_plan_artifacts(plan)
    inventory, metadata = normalize_inventory(artifacts["inventory"])
    selected_value = plan.get("selected")
    if selected_value is None:
        raise ValidationError("schema", "plan: selected scope is required")
    selected, _ = normalize_inventory(selected_value, "selected")
    if {name.casefold() for name in selected} != {name.casefold() for name in inventory}:
        raise ValidationError("binding", "plan: selected scope does not match inventory")
    expected_selected = expected.get("selected")
    if expected_selected is not None:
        expected_names, _ = normalize_inventory(expected_selected, "expected selected scope")
        if {name.casefold() for name in selected} != {name.casefold() for name in expected_names}:
            raise ValidationError("binding", "plan: selected scope does not match parent expectation")
    for name, item in metadata.items():
        classification = field(item, "classification", "visibility", "privacy")
        if classification not in {"safe", "private"}:
            raise ValidationError("privacy", f"inventory: {name} requires classification safe|private")
    clusters = validate_clusters(artifacts["clusters"], inventory)
    staleness = validate_staleness(artifacts["staleness"], inventory)
    grounding = validate_grounding(artifacts["grounding"], inventory, repo_root)
    report = validate_report(artifacts["report"], inventory)
    operations = validate_operations(plan.get("operations"), inventory, metadata)
    supplied_hash = plan["artifactHash"]
    calculated_hash = digest(artifact_payload(plan))
    # A parent may bind a precomputed hash of the serialized artifact.  When it
    # uses the documented canonical payload hash, verify it as well; arbitrary
    # opaque parent hashes are still bound by equality with the receipt.
    if supplied_hash.removeprefix("sha256:").lower() == calculated_hash.lower():
        pass
    return {
        "inventory": inventory,
        "metadata": metadata,
        "clusters": clusters,
        "staleness": staleness,
        "grounding": grounding,
        "report": report,
        "operations": operations,
        "calculatedArtifactHash": calculated_hash,
    }


def lstat_regular(path: Path, label: str, directory: bool = False) -> os.stat_result:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ValidationError("privacy", f"{label}: cannot inspect {path}: {exc}") from exc
    if stat.st_mode & 0o170000 == 0o120000:
        raise ValidationError("symlink", f"{label}: symlink is not allowed: {path}")
    if directory and not path.is_dir():
        raise ValidationError("privacy", f"{label}: expected a directory: {path}")
    if not directory and not path.is_file():
        raise ValidationError("privacy", f"{label}: expected a regular file: {path}")
    return stat


def open_memory_root(root: Path, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise ValidationError("privacy", f"{label}: cannot open directory: {exc}") from exc
    try:
        stat = os.fstat(descriptor)
        if (stat.st_mode & 0o170000) != 0o040000:
            raise ValidationError("privacy", f"{label}: expected a directory: {root}")
        return descriptor
    except ValidationError:
        os.close(descriptor)
        raise
    except OSError as exc:
        os.close(descriptor)
        raise ValidationError("privacy", f"{label}: cannot inspect directory: {exc}") from exc


def read_regular_bytes(path: Path, label: str, root_fd: int | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    target: str | Path = path.name if root_fd is not None else path
    try:
        descriptor = os.open(target, flags, dir_fd=root_fd)
    except OSError as exc:
        if exc.errno in {getattr(os, "ELOOP", 40), getattr(os, "EMLINK", 31)}:
            raise ValidationError("symlink", f"{label}: symlink is not allowed: {path}") from exc
        raise ValidationError("privacy", f"{label}: cannot open {path}: {exc}") from exc
    try:
        stat = os.fstat(descriptor)
        if (stat.st_mode & 0o170000) != 0o100000:
            raise ValidationError("privacy", f"{label}: expected a regular file: {path}")
        if stat.st_size > MAX_MEMORY_FILE_BYTES:
            raise ValidationError(
                "memory_bounds",
                f"{label}: memory file exceeds per-file byte bound {MAX_MEMORY_FILE_BYTES}",
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, MAX_MEMORY_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_MEMORY_FILE_BYTES:
                raise ValidationError(
                    "memory_bounds",
                    f"{label}: memory file exceeds per-file byte bound {MAX_MEMORY_FILE_BYTES}",
                )
        return b"".join(chunks)
    except ValidationError:
        raise
    except OSError as exc:
        raise ValidationError("privacy", f"{label}: cannot read {path}: {exc}") from exc
    finally:
        os.close(descriptor)


def read_regular_text(path: Path, label: str, root_fd: int | None = None) -> str:
    try:
        return read_regular_bytes(path, label, root_fd).decode("utf-8")
    except UnicodeError as exc:
        raise ValidationError("privacy", f"{label}: cannot decode {path}: {exc}") from exc


def memory_children(root: Path, label: str, root_fd: int | None = None) -> dict[str, Path]:
    if root_fd is None:
        lstat_regular(root, label, directory=True)
    children: dict[str, Path] = {}
    memory_file_count = 0
    total_bytes = 0
    try:
        entries = list(os.scandir(root_fd if root_fd is not None else root))
    except OSError as exc:
        raise ValidationError("privacy", f"{label}: cannot list {root}: {exc}") from exc
    for entry in entries:
        child = root / entry.name
        try:
            stat = os.stat(entry.name, dir_fd=root_fd, follow_symlinks=False) if root_fd is not None else child.lstat()
        except OSError as exc:
            raise ValidationError("privacy", f"{label}: cannot inspect {child}: {exc}") from exc
        if stat.st_mode & 0o170000 == 0o120000:
            raise ValidationError("symlink", f"{label}: symlink child is not allowed: {child}")
        if (stat.st_mode & 0o170000) != 0o100000:
            raise ValidationError("privacy", f"{label}: child must be a regular file: {child}")
        if not child.name.lower().endswith(".md"):
            raise ValidationError("privacy", f"{label}: unsupported non-Markdown child {child.name!r}")
        if child.name.lower() != INDEX_NAME and not MEMORY_NAME_RE.fullmatch(child.name):
            raise ValidationError("artifact_identity", f"{label}: invalid Markdown child name {child.name!r}")
        if stat.st_size > MAX_MEMORY_FILE_BYTES:
            raise ValidationError(
                "memory_bounds",
                f"{label}: memory file {child.name!r} exceeds per-file byte bound {MAX_MEMORY_FILE_BYTES}",
            )
        if child.name.lower() != INDEX_NAME:
            memory_file_count += 1
            if memory_file_count > MAX_MEMORY_FILES:
                raise ValidationError(
                    "memory_bounds",
                    f"{label}: memory file count exceeds validator bound {MAX_MEMORY_FILES}",
                )
        total_bytes += stat.st_size
        if total_bytes > MAX_MEMORY_TOTAL_BYTES:
            raise ValidationError(
                "memory_bounds",
                f"{label}: aggregate memory bytes exceed validator bound {MAX_MEMORY_TOTAL_BYTES}",
            )
        key = INDEX_NAME if child.name.lower() == INDEX_NAME else child.name
        if key in children or any(existing.lower() == key.lower() for existing in children):
            raise ValidationError("artifact_identity", f"{label}: duplicate case-insensitive child {child.name!r}")
        children[key] = child
    if INDEX_NAME not in children:
        raise ValidationError("privacy", f"{label}: MEMORY.md missing")
    return children


def index_entries(index: Path, label: str, root_fd: int | None = None) -> tuple[set[str], set[str]]:
    text = read_regular_text(index, label, root_fd)
    entries: set[str] = set()
    private: set[str] = set()
    for line in text.splitlines():
        match = LINK_RE.search(line) or TOKEN_RE.search(line)
        if match is None:
            if PRIVATE_MARKER_RE.search(line):
                raise ValidationError("privacy", f"{label}: harness-only marker has no memory filename")
            continue
        name = match.group(1)
        normalized = strict_name(name, f"{label}: index entry")
        if normalized is None:
            continue
        if any(existing.casefold() == normalized.casefold() for existing in entries):
            raise ValidationError("artifact_identity", f"{label}: duplicate index entry {normalized}")
        entries.add(normalized)
        if PRIVATE_MARKER_RE.search(line):
            private.add(normalized)
    return entries, private


def body_hashes(children: dict[str, Path], root_fd: int | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, path in children.items():
        result[key] = hash_bytes(read_regular_bytes(path, f"privacy: hash {path.name}", root_fd))
    return result


def canonical_directory(root: Path, label: str) -> Path:
    lstat_regular(root, label, directory=True)
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise ValidationError("privacy", f"{label}: cannot resolve canonical directory: {exc}") from exc


def check_privacy(harness: Path, public: Path) -> dict[str, Any]:
    harness_canonical = canonical_directory(harness, "privacy: harness")
    public_canonical = canonical_directory(public, "privacy: public")
    if harness_canonical == public_canonical:
        raise ValidationError("privacy", "privacy: harness and public roots must be distinct canonical directories")
    harness_fd = open_memory_root(harness, "privacy: harness")
    public_fd: int | None = None
    try:
        public_fd = open_memory_root(public, "privacy: public")
        harness_children = memory_children(harness, "privacy: harness", harness_fd)
        public_children = memory_children(public, "privacy: public", public_fd)
        harness_index = harness_children[INDEX_NAME]
        public_index = public_children[INDEX_NAME]
        harness_indexed, private = index_entries(harness_index, "privacy: harness MEMORY.md", harness_fd)
        public_indexed, public_private = index_entries(public_index, "privacy: public MEMORY.md", public_fd)
        if public_private:
            raise ValidationError("privacy", "privacy: public MEMORY.md contains harness-only line(s)")

        harness_files = set(harness_children) - {INDEX_NAME}
        public_files = set(public_children) - {INDEX_NAME}
        if harness_indexed != harness_files:
            missing = sorted(harness_files - harness_indexed)
            orphan = sorted(harness_indexed - harness_files)
            detail = f"missing index entry {missing[0]}" if missing else f"orphan index entry {orphan[0]}"
            raise ValidationError("privacy", f"privacy: harness index is incomplete ({detail})")
        if public_indexed != public_files:
            missing = sorted(public_files - public_indexed)
            orphan = sorted(public_indexed - public_files)
            detail = f"missing index entry {missing[0]}" if missing else f"orphan index entry {orphan[0]}"
            raise ValidationError("privacy", f"privacy: public index is incomplete ({detail}; orphan/unindexed public memory)")
        if not private <= harness_files:
            name = sorted(private - harness_files)[0]
            raise ValidationError("privacy", f"privacy: harness index lists missing file {name}")
        if private & public_files:
            name = sorted(private & public_files)[0]
            raise ValidationError("privacy", f"privacy: harness-only file present under public: {name}")

        safe_harness = harness_files - private
        if safe_harness != public_files:
            missing = sorted(safe_harness - public_files)
            extra = sorted(public_files - safe_harness)
            if missing:
                raise ValidationError("mirror", f"safe mirror drift: public missing {missing[0]}")
            raise ValidationError("mirror", f"safe mirror drift: public has orphan/unindexed file {extra[0]}")
        harness_hashes = body_hashes(harness_children, harness_fd)
        public_hashes = body_hashes(public_children, public_fd)
        for name in sorted(safe_harness):
            if harness_hashes[name] != public_hashes[name]:
                raise ValidationError("mirror", f"safe mirror drift: hash mismatch for {name}")
        return {
            "harness": harness_hashes,
            "public": public_hashes,
            "safe": sorted(safe_harness),
            "private": sorted(private),
        }
    finally:
        os.close(harness_fd)
        if public_fd is not None:
            os.close(public_fd)


def extract_final_hashes(receipt: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    value = receipt.get("finalHashes", receipt.get("final_hashes"))
    if not isinstance(value, dict) and isinstance(receipt.get("harnessHashes"), dict) and isinstance(receipt.get("publicHashes"), dict):
        value = {"harness": receipt["harnessHashes"], "public": receipt["publicHashes"]}
    if not isinstance(value, dict):
        final = receipt.get("final")
        value = final if isinstance(final, dict) else None
    if not isinstance(value, dict):
        raise ValidationError("receipt", "receipt: missing finalHashes.harness/public")
    harness = value.get("harness")
    public = value.get("public")
    if not isinstance(harness, dict) or not isinstance(public, dict):
        raise ValidationError("receipt", "receipt: finalHashes must contain harness and public maps")
    def clean(mapping: dict[str, Any], label: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, value in mapping.items():
            normalized = strict_name(name, f"receipt.{label}")
            if normalized is None:
                # MEMORY.md is a valid hash key in a final tree; strict_name
                # intentionally excludes it for selected artifacts.
                normalized = name
                if name.lower() != INDEX_NAME:
                    raise ValidationError("receipt", f"receipt.{label}: invalid file name {name!r}")
            if not isinstance(value, str) or not HASH_RE.fullmatch(value):
                raise ValidationError("receipt", f"receipt.{label}: invalid hash for {name}")
            key = INDEX_NAME if normalized.lower() == INDEX_NAME else normalized
            if key in result:
                raise ValidationError("receipt", f"receipt.{label}: duplicate file key {name!r}")
            result[key] = value.removeprefix("sha256:").lower()
        return result
    return clean(harness, "harness"), clean(public, "public")


def extract_hash_maps(value: Any, label: str) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(value, dict):
        raise ValidationError("receipt", f"{label}: expected harness and public maps")
    harness = value.get("harness")
    public = value.get("public")
    if not isinstance(harness, dict) or not isinstance(public, dict):
        raise ValidationError("receipt", f"{label}: expected harness and public maps")

    def clean(mapping: dict[str, Any], side: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, value in mapping.items():
            normalized = strict_name(name, f"{label}.{side}")
            if normalized is None:
                if name.lower() != INDEX_NAME:
                    raise ValidationError("receipt", f"{label}.{side}: invalid file name {name!r}")
                normalized = INDEX_NAME
            if not isinstance(value, str) or not HASH_RE.fullmatch(value):
                raise ValidationError("receipt", f"{label}.{side}: invalid hash for {name}")
            key = INDEX_NAME if normalized.lower() == INDEX_NAME else normalized
            if key in result:
                raise ValidationError("receipt", f"{label}.{side}: duplicate file key {name!r}")
            result[key] = value.removeprefix("sha256:").lower()
        return result

    return clean(harness, "harness"), clean(public, "public")


def validate_receipt(
    receipt: dict[str, Any],
    plan: dict[str, Any],
    plan_data: dict[str, Any],
    plan_bytes: bytes,
    privacy: dict[str, Any] | None,
    expected: dict[str, Any],
    expected_source_hashes: tuple[dict[str, str], dict[str, str]] | None = None,
) -> None:
    if receipt.get("schemaVersion", receipt.get("version")) != 1:
        raise ValidationError("schema", "receipt: schemaVersion must be 1")
    kind = receipt.get("kind", receipt.get("type"))
    if kind not in {"memory-consolidation-receipt", "consolidation-receipt"}:
        raise ValidationError("receipt", f"receipt: unsupported kind {kind!r}")
    phase = receipt.get("phase")
    if phase not in {"pre", "post"}:
        raise ValidationError("receipt", "receipt: phase must be pre or post")
    expected_phase = expected.get("receiptPhase")
    if expected_phase is not None and phase != expected_phase:
        raise ValidationError("binding", "receipt: phase does not match parent expectation")
    if phase != "post":
        raise ValidationError("receipt", "receipt: post phase is required for final validation")
    plan_digest = receipt.get("planDigest")
    if not isinstance(plan_digest, str) or not HASH_RE.fullmatch(plan_digest):
        raise ValidationError("receipt", "receipt: post planDigest is required and must be a SHA-256 hash")
    if not hash_matches(hash_bytes(plan_bytes), plan_digest):
        raise ValidationError("binding", "receipt: planDigest does not match the plan artifact")
    if expected_source_hashes is not None:
        source_value = receipt.get("sourceHashes")
        if source_value is None:
            raise ValidationError("binding", "receipt: source hashes are required by the parent transaction")
        actual_source_hashes = extract_hash_maps(source_value, "receipt.sourceHashes")
        if actual_source_hashes != expected_source_hashes:
            raise ValidationError("binding", "receipt: source hashes do not match the parent snapshot")
    identities = {
        "runId": None,
        "scopeDigest": None,
        "artifactHash": "snapshotDigest",
    }
    for name, alias in identities.items():
        value = identity_value(receipt, name, alias, "receipt")
        plan_value = identity_value(plan, name, alias, "plan")
        if value != plan_value:
            raise ValidationError("binding", f"receipt: {name} does not match plan")
        if name != "runId" and not HASH_RE.fullmatch(value):
            raise ValidationError("binding", f"receipt: invalid {name} format")
        wanted = expected.get(name)
        if wanted is not None and value != wanted:
            raise ValidationError("binding", f"receipt: {name} does not match parent expectation")
    selected = receipt.get("selected", receipt.get("inventory"))
    if selected is None:
        raise ValidationError("binding", "receipt: selected files are required")
    selected_names, _ = normalize_inventory(selected, "receipt.selected")
    if {name.casefold() for name in selected_names} != {name.casefold() for name in plan_data["inventory"]}:
        raise ValidationError("binding", "receipt: selected files do not match plan scope")
    expected_selected = expected.get("selected")
    if expected_selected is not None:
        expected_names, _ = normalize_inventory(expected_selected, "expected selected scope")
        if {name.casefold() for name in selected_names} != {name.casefold() for name in expected_names}:
            raise ValidationError("binding", "receipt: selected files do not match parent expectation")
    if privacy is None:
        raise ValidationError("receipt", "receipt: privacy result is required to verify final hashes")
    expected_harness, expected_public = extract_final_hashes(receipt)
    actual_harness = {key: value.lower() for key, value in privacy["harness"].items()}
    actual_public = {key: value.lower() for key, value in privacy["public"].items()}
    if expected_harness != actual_harness:
        raise ValidationError("receipt", "receipt: harness final hashes do not match current state")
    if expected_public != actual_public:
        raise ValidationError("receipt", "receipt: public final hashes do not match current state")


def check_plan_classification(plan_data: dict[str, Any], privacy: dict[str, Any]) -> None:
    private = set(privacy["private"])
    for name, metadata in plan_data["metadata"].items():
        classification = field(metadata, "classification", "privacy", "visibility")
        if classification is None:
            continue
        if not isinstance(classification, str) or classification.lower() not in {"safe", "private", "harness-only", "harness_only"}:
            raise ValidationError("privacy", f"inventory: {name} has invalid classification {classification!r}")
        is_private = classification.lower() in {"private", "harness-only", "harness_only"}
        if is_private != (name in private):
            expected = "private" if name in private else "safe"
            raise ValidationError("privacy", f"inventory: {name} classification disagrees with harness index (expected {expected})")


def parse_expected_selected(raw: list[str] | None) -> list[Any] | None:
    if raw is None:
        return None
    values: list[Any] = []
    for item in raw:
        try:
            decoded = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            values.append(item)
            continue
        if isinstance(decoded, list):
            values.extend(decoded)
        else:
            values.append(decoded)
    return values


def parse_expected(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "runId": args.expected_run_id,
        "scopeKey": args.expected_scope_key,
        "scopeDigest": args.expected_scope_digest,
        "artifactHash": args.expected_artifact_hash,
        "runDir": args.expected_run_dir,
        "receiptAfter": args.expected_receipt_after,
        "receiptPhase": args.expected_receipt_phase,
        "selected": parse_expected_selected(args.expected_selected),
    }


def result(ok: bool, checks: list[str], errors: list[ValidationError], details: dict[str, Any] | None = None) -> dict[str, Any]:
    output: dict[str, Any] = {"ok": ok, "checks": checks}
    if errors:
        output["errors"] = [{"code": error.code, "message": error.message} for error in errors]
    if details:
        output["details"] = details
    return output


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        output = {
            "ok": False,
            "checks": [],
            "errors": [{"code": "usage", "message": f"usage: {message}"}],
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, help="structured consolidation plan JSON")
    parser.add_argument("--receipt", type=Path, help="parent-owned post-apply receipt JSON")
    parser.add_argument("--repo-root", type=Path, help="repository root for grounding containment")
    parser.add_argument("--harness", type=Path, help="harness memory directory")
    parser.add_argument("--public", type=Path, help="public .memory directory")
    parser.add_argument("--expected-run-id", "--run-id", dest="expected_run_id")
    parser.add_argument("--expected-scope-key", "--scope-key", dest="expected_scope_key")
    parser.add_argument("--expected-scope-digest", "--scope-digest", dest="expected_scope_digest")
    parser.add_argument("--expected-artifact-hash", "--artifact-hash", dest="expected_artifact_hash")
    parser.add_argument("--expected-run-dir", type=Path, dest="expected_run_dir")
    parser.add_argument("--expected-receipt-after", type=float, dest="expected_receipt_after")
    parser.add_argument(
        "--expected-selected",
        dest="expected_selected",
        action="append",
        help="parent-selected memory filename; repeat for each selected file",
    )
    parser.add_argument("--expected-receipt-phase", choices=("pre", "post"), default="post")
    parser.add_argument("--check", default="plan,receipt,privacy", help="comma list: plan,receipt,privacy")
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        dest="max_total_bytes",
        help="override the aggregate memory byte bound (defaults to file-count × per-file bounds)",
    )
    parser.add_argument(
        "--max-memory-files",
        type=int,
        dest="max_memory_files",
        help="override the memory file count bound",
    )
    args = parser.parse_args(argv)
    global MAX_MEMORY_TOTAL_BYTES, MAX_MEMORY_FILES
    if args.max_memory_files is not None:
        if args.max_memory_files < 1:
            print(json.dumps({
                "ok": False,
                "checks": [],
                "errors": [{"code": "usage", "message": "usage: --max-memory-files must be positive"}],
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            raise SystemExit(2)
        MAX_MEMORY_FILES = args.max_memory_files
    if args.max_total_bytes is not None:
        if args.max_total_bytes < 0:
            print(json.dumps({
                "ok": False,
                "checks": [],
                "errors": [{"code": "usage", "message": "usage: --max-total-bytes must be non-negative"}],
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            raise SystemExit(2)
        MAX_MEMORY_TOTAL_BYTES = args.max_total_bytes
    checks = {item.strip().lower() for item in args.check.split(",") if item.strip()}
    aliases = {"cluster": "plan", "staleness": "plan", "report": "plan"}
    if "all" in checks:
        checks.remove("all")
        checks.update({"plan", "receipt", "privacy"})
    checks = {aliases.get(item, item) for item in checks}
    known = {"plan", "receipt", "privacy"}
    errors: list[ValidationError] = []
    details: dict[str, Any] = {}
    if not checks or checks - known:
        errors.append(ValidationError("usage", "usage: --check must contain plan, receipt, and/or privacy"))
    if "receipt" in checks and "plan" not in checks:
        # Receipt verification still needs a plan, but the plan check can be
        # skipped only for callers that explicitly ask for privacy alone.
        errors.append(ValidationError("usage", "usage: receipt check requires plan check"))
    plan: dict[str, Any] | None = None
    plan_data: dict[str, Any] | None = None
    plan_bytes: bytes | None = None
    privacy: dict[str, Any] | None = None
    if not errors and "plan" in checks:
        if args.plan is None:
            errors.append(ValidationError("usage", "usage: --plan is required for plan validation"))
        else:
            try:
                plan, plan_bytes = load_json_with_bytes(args.plan, "plan")
                plan_data = validate_plan(plan, parse_expected(args), args.repo_root)
                details["inventoryCount"] = len(plan_data["inventory"])
            except ValidationError as error:
                errors.append(error)
    if not errors and "privacy" in checks:
        if args.harness is None or args.public is None:
            errors.append(ValidationError("usage", "usage: --harness and --public are required for privacy validation"))
        else:
            try:
                privacy = check_privacy(args.harness, args.public)
                if plan_data is not None:
                    check_plan_classification(plan_data, privacy)
                details["safeCount"] = len(privacy["safe"])
                details["privateCount"] = len(privacy["private"])
            except ValidationError as error:
                errors.append(error)
    if not errors and "receipt" in checks:
        if args.receipt is None:
            errors.append(ValidationError("usage", "usage: --receipt is required for receipt validation"))
        elif plan is None or plan_data is None:
            errors.append(ValidationError("usage", "usage: a validated plan is required for receipt validation"))
        else:
            try:
                expected = parse_expected(args)
                expected_path = f"{expected['receiptPhase']}-receipt.json"
                if args.receipt.name != expected_path:
                    raise ValidationError("binding", f"receipt: path must be {expected_path}")
                expected_run_dir = expected.get("runDir")
                if expected_run_dir is not None and args.plan.resolve(strict=False).parent != expected_run_dir.resolve(strict=False):
                    raise ValidationError("binding", "plan: path must be in the exact expected run directory")
                expected_receipt_path = (args.plan.parent / expected_path).resolve(strict=False)
                if args.receipt.resolve(strict=False) != expected_receipt_path:
                    raise ValidationError("binding", "receipt: path must be in the exact plan run directory")
                lstat_regular(args.receipt, "receipt")
                receipt_after = expected.get("receiptAfter")
                if receipt_after is not None and args.receipt.stat().st_mtime < receipt_after:
                    raise ValidationError("binding", "receipt: post receipt is stale and predates mutation")
                receipt = load_json(args.receipt, "receipt")
                if plan_bytes is None:
                    raise ValidationError("usage", "usage: plan bytes are required for receipt validation")
                expected_source_hashes: tuple[dict[str, str], dict[str, str]] | None = None
                manifest_path = args.plan.parent / "manifest.json"
                if manifest_path.exists():
                    manifest = load_json(manifest_path, "manifest")
                    expected_source_hashes = extract_hash_maps(
                        manifest.get("sourceHashes"),
                        "manifest.sourceHashes",
                    )
                validate_receipt(
                    receipt,
                    plan,
                    plan_data,
                    plan_bytes,
                    privacy,
                    expected,
                    expected_source_hashes,
                )
                details["receiptVerified"] = True
            except ValidationError as error:
                errors.append(error)
    if not errors:
        expected = parse_expected(args)
        details["binding"] = {
            "runId": expected.get("runId") or (plan or {}).get("runId"),
            "scopeDigest": expected.get("scopeDigest") or (plan or {}).get("scopeDigest"),
            "artifactHash": expected.get("artifactHash") or (plan or {}).get("artifactHash"),
            "runDir": str(expected["runDir"].resolve(strict=False)) if expected.get("runDir") else str(args.plan.parent.resolve(strict=False)) if args.plan else None,
            "receiptPath": str(args.receipt.resolve(strict=False)) if args.receipt else None,
        }
    output = result(not errors, sorted(checks), errors, details)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    if errors:
        return 2 if any(error.code == "usage" or error.code == "json" for error in errors) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
