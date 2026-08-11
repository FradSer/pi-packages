#!/usr/bin/env python3
"""Validate /skill:consolidate planning artifacts and privacy split.

Machine-checks what prompt gates cannot: cluster covers inventory, staleness
covers inventory, report cites ground-truth paths, private files stay out of
public .memory/.

Usage:
  python3 validate-consolidate.py \\
    --inventory inventory.txt \\
    --cluster cluster.txt \\
    --staleness staleness.txt \\
    --report report.md \\
    --harness ~/.claude/projects/.../memory \\
    --public .memory \\
    [--check=cluster,staleness,report,privacy]

  # Pre-mutation (freeze lift): cluster + staleness only
  python3 validate-consolidate.py --inventory I --cluster C --staleness S \\
    --check=cluster,staleness

Exit codes:
  0 — all selected checks passed
  1 — one or more checks failed
  2 — usage / IO error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VALID_VERDICTS = frozenset(
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

INDEX_NAMES = frozenset({"MEMORY.md", "memory.md"})

# path → found|missing|updated  (ascii arrow or unicode)
PATH_ARROW_RE = re.compile(
    r"(?m)^[ \t]*[`'\"\[]?[\w./@+-]+[`'\"\]]?[ \t]*(?:→|->)[ \t]*"
    r"(?:found|missing|updated)\b",
    re.IGNORECASE,
)
NA_REPO_RE = re.compile(
    r"N/A\s*\(\s*no\s+repo\s*\)|Ground\s+truth:\s*N/A",
    re.IGNORECASE,
)
HARNESS_ONLY_RE = re.compile(r"\(harness\s+only\)", re.IGNORECASE)
# index line: "- [foo.md](foo.md) — …" or "foo.md — …"
INDEX_FILE_RE = re.compile(
    r"(?m)^[ \t]*(?:-\s+)?(?:\[[^\]]+\]\(([^)]+\.md)\)|(`?)([\w./-]+\.md)\2)"
    r".*?\(harness\s+only\)",
    re.IGNORECASE,
)
CLUSTER_HEADER_RE = re.compile(r"(?mi)^cluster:\s*(.+?)\s*$")
CLUSTER_ITEM_RE = re.compile(r"(?m)^[ \t]*-\s+(`?)([\w./-]+\.md)\1\s*$")
STALENESS_LINE_RE = re.compile(
    r"(?m)^[ \t]*(?:\|\s*)?(`?)([\w./-]+\.md)\1\s*"
    r"(?:[|:—-]\s*)?([A-Z][A-Z0-9_-]*)\b"
)


def parse_inventory(text: str) -> list[str]:
    files: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # allow "- foo.md" or "foo.md"
        line = re.sub(r"^-\s+", "", line)
        line = line.strip("`")
        name = Path(line).name
        if name in INDEX_NAMES:
            continue
        if not name.endswith(".md"):
            continue
        files.append(name)
    return files


def parse_cluster(text: str) -> dict[str, list[str]]:
    """Return {cluster_name: [files...]} preserving order."""
    clusters: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        header = CLUSTER_HEADER_RE.match(raw)
        if header:
            current = header.group(1).strip()
            clusters.setdefault(current, [])
            continue
        item = CLUSTER_ITEM_RE.match(raw)
        if item and current is not None:
            clusters[current].append(Path(item.group(2)).name)
    return clusters


def cluster_membership(clusters: dict[str, list[str]]) -> dict[str, list[str]]:
    """file -> list of cluster names it appears in."""
    membership: dict[str, list[str]] = {}
    for name, files in clusters.items():
        for f in files:
            membership.setdefault(f, []).append(name)
    return membership


def parse_staleness(text: str) -> dict[str, str]:
    scores: dict[str, str] = {}
    for m in STALENESS_LINE_RE.finditer(text):
        fname = Path(m.group(2)).name
        verdict = m.group(3).upper().replace(" ", "-")
        # normalize OPS_ONLY -> OPS-ONLY
        verdict = verdict.replace("_", "-")
        if fname in INDEX_NAMES:
            continue
        scores[fname] = verdict
    return scores


def check_cluster(inventory: list[str], cluster_text: str) -> list[str]:
    errors: list[str] = []
    clusters = parse_cluster(cluster_text)
    if not clusters:
        return ["cluster: no 'cluster:' headers found"]
    membership = cluster_membership(clusters)
    inv_set = set(inventory)

    for f in inventory:
        homes = membership.get(f, [])
        if not homes:
            errors.append(f"cluster: {f} missing from cluster map")
        elif len(homes) > 1:
            errors.append(
                f"cluster: {f} duplicate in clusters {', '.join(homes)}"
            )

    for f, homes in membership.items():
        if f not in inv_set:
            errors.append(f"cluster: {f} not in inventory (in {homes[0]})")
        if len(homes) > 1 and f in inv_set:
            # already reported above for inv files; still catch pure dups
            pass

    return errors


def check_staleness(inventory: list[str], staleness_text: str) -> list[str]:
    errors: list[str] = []
    scores = parse_staleness(staleness_text)
    if not scores and inventory:
        return ["staleness: no scored files found"]

    for f in inventory:
        if f not in scores:
            errors.append(f"staleness: {f} missing from staleness table")
            continue
        v = scores[f]
        if v not in VALID_VERDICTS:
            errors.append(f"staleness: {f} invalid verdict {v}")

    for f, v in scores.items():
        if f not in inventory and f not in INDEX_NAMES:
            errors.append(f"staleness: {f} not in inventory")
        if v not in VALID_VERDICTS and f in inventory:
            pass  # already flagged

    return errors


def inventory_has_project(inventory: list[str]) -> bool:
    return any(Path(f).name.startswith("project_") for f in inventory)


def check_report(inventory: list[str], report_text: str) -> list[str]:
    errors: list[str] = []
    if not report_text.strip():
        return ["report: empty"]

    has_path = bool(PATH_ARROW_RE.search(report_text))
    has_na = bool(NA_REPO_RE.search(report_text))

    if inventory_has_project(inventory):
        if not has_path and not has_na:
            errors.append(
                "report: project_* present but no 'path → found|missing|updated' "
                "row and no 'N/A (no repo)' ground-truth"
            )
    # feedback-only inventory: path rows optional
    return errors


def harness_only_files_from_index(index_text: str) -> set[str]:
    found: set[str] = set()
    for m in INDEX_FILE_RE.finditer(index_text):
        name = m.group(1) or m.group(3)
        if name:
            found.add(Path(name).name)
    # fallback: any line with harness only and a .md token
    for line in index_text.splitlines():
        if not HARNESS_ONLY_RE.search(line):
            continue
        for token in re.findall(r"[\w./-]+\.md", line):
            found.add(Path(token).name)
    return found


def check_privacy(harness: Path, public: Path) -> list[str]:
    errors: list[str] = []
    if not harness.is_dir():
        return [f"privacy: harness not a directory: {harness}"]
    if not public.is_dir():
        return [f"privacy: public not a directory: {public}"]

    harness_index = harness / "MEMORY.md"
    public_index = public / "MEMORY.md"

    private: set[str] = set()
    if harness_index.is_file():
        private = harness_only_files_from_index(harness_index.read_text(encoding="utf-8"))
    else:
        errors.append("privacy: harness MEMORY.md missing")

    if public_index.is_file():
        pub_text = public_index.read_text(encoding="utf-8")
        if HARNESS_ONLY_RE.search(pub_text):
            errors.append(
                "privacy: public MEMORY.md contains (harness only) line(s)"
            )
        # any private name mentioned in public index
        for name in private:
            if re.search(rf"\b{re.escape(name)}\b", pub_text):
                errors.append(
                    f"privacy: public MEMORY.md lists harness-only file {name}"
                )
    else:
        # public index optional only if public dir empty of md — still warn soft?
        pub_mds = list(public.glob("*.md"))
        if pub_mds:
            errors.append("privacy: public MEMORY.md missing while .md files exist")

    for name in sorted(private):
        leak = public / name
        if leak.is_file():
            errors.append(
                f"privacy: harness-only file present under public: {name}"
            )

    return errors


def read_text(path: Path | None) -> str:
    if path is None:
        return ""
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory", type=Path, help="inventory file (one .md per line)")
    p.add_argument("--cluster", type=Path, help="cluster map file")
    p.add_argument("--staleness", type=Path, help="staleness table file")
    p.add_argument("--report", type=Path, help="consolidate report file")
    p.add_argument("--harness", type=Path, help="harness memory directory")
    p.add_argument("--public", type=Path, help="public .memory directory")
    p.add_argument(
        "--check",
        default="cluster,staleness,report,privacy",
        help="comma list: cluster,staleness,report,privacy",
    )
    args = p.parse_args(argv)

    checks = {c.strip().lower() for c in args.check.split(",") if c.strip()}
    known = {"cluster", "staleness", "report", "privacy"}
    unknown = checks - known
    if unknown:
        print(f"usage: unknown check(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    if not checks:
        print("usage: --check empty", file=sys.stderr)
        return 2

    errors: list[str] = []
    inventory: list[str] = []

    needs_inv = checks & {"cluster", "staleness", "report"}
    if needs_inv:
        if not args.inventory or not args.inventory.is_file():
            print("usage: --inventory required and must exist for selected checks", file=sys.stderr)
            return 2
        try:
            inventory = parse_inventory(read_text(args.inventory))
        except OSError as e:
            print(f"io: inventory: {e}", file=sys.stderr)
            return 2
        if not inventory:
            errors.append("inventory: no memory files listed (empty after filtering MEMORY.md)")

    try:
        if "cluster" in checks:
            if not args.cluster or not args.cluster.is_file():
                print("usage: --cluster required for cluster check", file=sys.stderr)
                return 2
            errors.extend(check_cluster(inventory, read_text(args.cluster)))

        if "staleness" in checks:
            if not args.staleness or not args.staleness.is_file():
                print("usage: --staleness required for staleness check", file=sys.stderr)
                return 2
            errors.extend(check_staleness(inventory, read_text(args.staleness)))

        if "report" in checks:
            if not args.report or not args.report.is_file():
                print("usage: --report required for report check", file=sys.stderr)
                return 2
            errors.extend(check_report(inventory, read_text(args.report)))

        if "privacy" in checks:
            if not args.harness or not args.public:
                print("usage: --harness and --public required for privacy check", file=sys.stderr)
                return 2
            errors.extend(check_privacy(args.harness, args.public))
    except OSError as e:
        print(f"io: {e}", file=sys.stderr)
        return 2

    if errors:
        print(f"FAILED  {len(errors)} issue(s)", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"PASSED  checks={','.join(sorted(checks))} inventory={len(inventory)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
