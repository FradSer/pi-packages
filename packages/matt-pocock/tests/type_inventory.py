"""Catalog-derived inventory. Listing coverage never starts Pi or reads auth."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from real_model_live import load_cases

PACKAGE = Path(__file__).resolve().parents[1]
CASE_FILES = ("real-model-cases.json", "developer-journey-cases.json", "expanded-type-cases.json")


def inventory(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    catalog = json.loads((PACKAGE / "src/catalog.json").read_text())
    if cases is None:
        cases = [case for name in CASE_FILES for case in load_cases(PACKAGE / "tests" / name)]
    sources = {source for case in cases for source in (
        [case["expectSource"]] if isinstance(case.get("expectSource"), str) else case.get("expectSource", [])
    )}
    routes = {case.get("route") for case in cases}
    standalone = [entry["id"] for entry in catalog if entry.get("standalone")]
    workflow_routes = {place["route"] for entry in catalog for place in entry.get("workflows", []) if place.get("entry")}
    missing = [f"standalone:{name}" for name in standalone if name not in sources]
    missing += [f"route:{name}" for name in sorted(workflow_routes - routes)]
    return {
        "resources": len(catalog),
        "resourceKinds": sorted({entry["kind"] for entry in catalog}),
        "invocationModes": sorted({entry["invocation"] for entry in catalog}),
        "standalone": standalone,
        "routes": sorted(workflow_routes),
        "placements": sum(len(entry.get("workflows", [])) for entry in catalog),
        "transitions": sum(len(place["allowedNext"]) for entry in catalog for place in entry.get("workflows", [])),
        "requires": sum(len(entry.get("requires", [])) for entry in catalog),
        "disclosures": sum(len(entry.get("discloses", [])) for entry in catalog),
        "aliases": sum(len(entry.get("aliases", [])) for entry in catalog),
        "realCases": len(cases),
        "developerTypes": sorted({case["fixture"] for case in cases if case["id"].startswith(("developer-", "type-"))}),
        "missingPublicTypes": missing,
    }


if __name__ == "__main__":
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
