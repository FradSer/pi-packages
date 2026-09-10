from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]


def run_typescript(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "--import", "tsx/esm", "--input-type=module"],
        cwd=REPO,
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_catalog_classifies_every_bundled_resource_and_resolves_all_edges() -> None:
    result = run_typescript("""
        import { catalogFiles, procedureCatalog, validateProcedureCatalog } from "./packages/matt-pocock/src/catalog.ts";
        import { readdirSync } from "node:fs";
        import { fileURLToPath } from "node:url";

        const directory = fileURLToPath(new URL("./packages/matt-pocock/procedures/", import.meta.url));
        const bundled = readdirSync(directory).sort();
        console.log(JSON.stringify({
          bundled,
          catalogFiles: catalogFiles().sort(),
          ids: procedureCatalog.map((entry) => entry.id),
          errors: validateProcedureCatalog(),
        }));
    """)
    assert result["errors"] == []
    assert result["catalogFiles"] == result["bundled"]
    assert len(result["ids"]) == len(set(result["ids"]))


def test_each_workflow_route_has_one_catalog_entry_with_display_metadata() -> None:
    result = run_typescript("""
        import { procedureCatalog, workflowRoutes } from "./packages/matt-pocock/src/catalog.ts";
        const entries = procedureCatalog.flatMap((definition) => (definition.workflows ?? [])
          .filter((workflow) => workflow.entry)
          .map((workflow) => ({ route: workflow.route, procedure: definition.id })));
        console.log(JSON.stringify({ routes: workflowRoutes(), entries }));
    """)
    assert [route["route"] for route in result["routes"]] == [
        "idea-to-ship", "hard-bug", "triage", "wayfinding", "architecture",
    ]
    assert result["entries"][0] == {"route": "idea-to-ship", "procedure": "grill-with-docs"}
    assert len(result["entries"]) == len(result["routes"])
    assert all(route["title"] and route["label"] and route["description"] for route in result["routes"])


def test_architecture_entry_loads_required_vocabulary_and_discloses_optional_references() -> None:
    result = run_typescript("""
        import { MAX_PROCEDURE_BUNDLE_BYTES, resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        const bundle = resolveProcedureBundle("improve-codebase-architecture");
        console.log(JSON.stringify({
          loaded: bundle.loaded,
          availableReferences: bundle.availableReferences,
          bytes: bundle.byteLength,
          maxBytes: MAX_PROCEDURE_BUNDLE_BYTES,
          content: bundle.content,
        }));
    """)
    assert result["loaded"] == ["improve-codebase-architecture", "codebase-design"]
    assert "HTML-REPORT" in result["availableReferences"]
    assert "grilling" in result["availableReferences"]
    assert "domain-modeling" in result["availableReferences"]
    assert "# Improve Codebase Architecture" in result["content"]
    assert "# Codebase Design" in result["content"]
    assert "](procedure:codebase-design)" in result["content"]
    assert "](codebase-design.md)" not in result["content"]
    assert 'source="procedure/improve-codebase-architecture"' in result["content"]
    assert 'source="procedure/codebase-design"' in result["content"]
    assert "Full HTML Report Scaffold" not in result["content"]
    assert "](procedure:codebase-design)" in result["content"]
    assert "](codebase-design.md)" not in result["content"]
    assert result["bytes"] <= result["maxBytes"]


def test_transition_graph_rejects_invalid_edges_instead_of_restarting() -> None:
    result = run_typescript("""
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const state = {
          version: 1, workItemId: "work-1", route: "architecture",
          procedure: "improve-codebase-architecture", phase: "survey",
          status: "active", loadedReferences: [],
        };
        const valid = transitionState(state, "implement");
        let invalid = "";
        try { transitionState(state, "wayfinder"); } catch (error) { invalid = String(error); }
        console.log(JSON.stringify({ valid, invalid }));
    """)
    assert result["valid"]["procedure"] == "implement"
    assert result["valid"]["phase"] == "implement"
    assert "Allowed next procedures: implement, code-review" in result["invalid"]


def test_standalone_capability_inventory_preserves_invocation_modes() -> None:
    result = run_typescript("""
        import { modelStandaloneCapabilities, standaloneCapabilities } from "./packages/matt-pocock/src/catalog.ts";
        console.log(JSON.stringify({
          all: standaloneCapabilities().map((entry) => entry.id),
          model: modelStandaloneCapabilities().map((entry) => entry.id),
        }));
    """)
    assert "writing-for-agents" in result["all"]
    assert "writing-for-agents" in result["model"]
    assert "resolving-merge-conflicts" in result["model"]
    assert "wizard" in result["model"]
    assert "deslop" in result["all"]
    assert "deslop" in result["model"]
    assert "setup-matt-pocock-skills" in result["all"]
    assert "setup-matt-pocock-skills" not in result["model"]
    assert "teach" in result["all"]
    assert "teach" not in result["model"]


def test_conditional_reference_access_is_scoped_to_the_active_procedure() -> None:
    result = run_typescript("""
        import { resolveAccessibleReference } from "./packages/matt-pocock/src/resolver.ts";
        const html = resolveAccessibleReference("improve-codebase-architecture", [], "HTML-REPORT");
        let error = "";
        try {
          resolveAccessibleReference("improve-codebase-architecture", [], "MISSION-FORMAT");
        } catch (caught) {
          error = String(caught);
        }
        console.log(JSON.stringify({ html, error }));
    """)
    assert result["html"]["loaded"] == ["HTML-REPORT"]
    assert 'source="procedure/HTML-REPORT"' in result["html"]["content"]
    assert "is not disclosed" in result["error"]
    assert "HTML-REPORT" in result["error"]


def test_required_dependencies_contribute_conditional_disclosures() -> None:
    result = run_typescript("""
        import { resolveAccessibleReference } from "./packages/matt-pocock/src/resolver.ts";
        const bundle = resolveAccessibleReference("improve-codebase-architecture", [], "DEEPENING");
        console.log(JSON.stringify(bundle));
    """)
    assert result["loaded"] == ["DEEPENING"]
    assert 'source="procedure/DEEPENING"' in result["content"]


def test_restored_bundle_replays_loaded_reference_chain() -> None:
    result = run_typescript("""
        import { resolveWorkflowContext } from "./packages/matt-pocock/src/resolver.ts";
        const bundle = resolveWorkflowContext("writing-for-agents", ["SKILL-MECHANICS", "writing-for-agents"]);
        console.log(JSON.stringify(bundle));
    """)
    assert result["loaded"] == ["writing-for-agents", "SKILL-MECHANICS"]
    assert result["content"].count('source="procedure/writing-for-agents"') == 1
    assert result["content"].count('source="procedure/SKILL-MECHANICS"') == 1
    assert "writing-great-skills" in result["availableReferences"]


def test_feature_file_covers_catalog_gateway_and_lifecycle_contracts() -> None:
    feature = (PACKAGE / "features" / "matt-pocock.feature").read_text()
    for scenario in (
        "The catalog is the single source of procedure truth",
        "Starting a workflow loads its mandatory dependency closure",
        "A workflow advertises only legal next transitions",
        "The agent explicitly completes or cancels a workflow",
        "Standalone capabilities are reachable without child skills",
        "A de-slop capability removes AI slop without workflow state",
        "The standards baseline rejects AI slop patterns in code review",
        "A local-only capability stays out of the upstream selection metadata",
        "Conditional references load through the active gateway",
        "Procedure texts route agents through the catalog gateway, not Pi skills",
        "Loaded references survive workflow restoration",
        "The active gateway is progressively disclosed",
        "Upstream synchronization metadata is verifiable",
    ):
        assert scenario in feature


def test_procedure_texts_route_agents_through_the_catalog_gateway() -> None:
    catalog = json.loads((PACKAGE / "src" / "catalog.json").read_text())
    patterns = {
        "catalog procedure called a skill": re.compile(r"\]\([^)]*\.md\) skills?\b"),
        "skill armed as loadable state": re.compile(r"skills? (loaded|active|together)\b"),
        "model runs user-invoked setup": re.compile(
            r"run \[setup-matt-pocock-skills\]\(setup-matt-pocock-skills\.md\)"
        ),
        "pointer at the Pi skill index": re.compile(r"available_skills"),
    }
    violations = []
    for entry in catalog:
        lines = (PACKAGE / "procedures" / entry["file"]).read_text().splitlines()
        for number, line in enumerate(lines, start=1):
            for label, pattern in patterns.items():
                if pattern.search(line):
                    violations.append(f"{entry['file']}:{number}: {label}: {line.strip()}")
    assert violations == []
