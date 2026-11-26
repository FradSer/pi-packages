from __future__ import annotations



# ── test_catalog.py ──

import json
import re

from matt_pocock_helpers import PACKAGE, run_typescript


def test_catalog_classifies_every_bundled_resource_and_resolves_all_edges() -> None:
    result = run_typescript("""
        import { findProcedure, procedureCatalog, resourcePath, validateProcedureCatalog } from "./packages/matt-pocock/src/catalog.ts";
        import { readdirSync } from "node:fs";
        import { dirname } from "node:path";

        const byKind = {};
        for (const kind of ["workflow", "utility", "reference", "asset"]) {
          const dir = dirname(resourcePath({ id: "x", file: "x", kind, invocation: "model", label: "x" }));
          byKind[kind] = readdirSync(dir).sort();
        }
        const bundled = [...new Set(Object.values(byKind).flat())].sort();
        const misplaced = procedureCatalog
          .filter((entry) => !byKind[entry.kind].includes(entry.file))
          .map((entry) => `${entry.id}: ${entry.file} is not filed under ${entry.kind}`);
        console.log(JSON.stringify({
          byKind,
          bundled,
          misplaced,
          catalogFiles: procedureCatalog.map((entry) => entry.file).sort(),
          ids: procedureCatalog.map((entry) => entry.id),
          errors: validateProcedureCatalog(),
          aliases: [findProcedure("tight-red-loop")?.id, findProcedure("clarify-goal")?.id],
        }));
    """)
    assert result["errors"] == []
    assert result["catalogFiles"] == result["bundled"]
    # The catalogue's kind decides the directory, so a file cannot be filed elsewhere.
    assert result["misplaced"] == []
    assert result["byKind"]["workflow"] == [entry for entry in result["byKind"]["workflow"]]
    assert all(name.endswith((".md", ".sh")) for name in result["bundled"])
    assert set(result["byKind"]) == {"workflow", "utility", "reference", "asset"}
    assert "code-review.md" in result["byKind"]["workflow"]
    assert "DEEPENING.md" in result["byKind"]["reference"]
    assert "code-review.md" not in result["byKind"]["reference"]
    assert "template.sh" in result["byKind"]["asset"]
    assert len(result["ids"]) == len(set(result["ids"]))
    assert result["aliases"] == ["diagnosing-bugs", "wayfinder"]


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
          root: bundle.root,
          loaded: bundle.loaded,
          availableReferences: bundle.availableReferences,
          bytes: bundle.byteLength,
          maxBytes: MAX_PROCEDURE_BUNDLE_BYTES,
          content: bundle.content,
        }));
    """)
    assert result["root"] == "improve-codebase-architecture"
    assert result["maxBytes"] == 64 * 1024
    assert result["loaded"] == ["improve-codebase-architecture", "codebase-design"]
    assert "HTML-REPORT" in result["availableReferences"]
    assert "grilling" in result["availableReferences"]
    assert "domain-modeling" in result["availableReferences"]
    assert "# Improve Codebase Architecture" in result["content"]
    assert "# Codebase Design" in result["content"]
    assert "](procedure:codebase-design)" in result["content"]
    assert "](codebase-design.md)" not in result["content"]
    # Links crossing a kind directory resolve to the same procedure link.
    assert "](../references/" not in result["content"]
    assert "](procedure:DEEPENING)" in result["content"]
    assert "](procedure:DESIGN-IT-TWICE)" in result["content"]
    assert 'source="procedure/improve-codebase-architecture"' in result["content"]
    assert 'source="procedure/codebase-design"' in result["content"]
    assert "Full HTML Report Scaffold" not in result["content"]
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
    assert "Allowed next procedures: codebase-design, implement, code-review" in result["invalid"]


def test_readable_phase_title_maps_triage_to_task_triage() -> None:
    result = run_typescript("""
        import { readablePhaseTitle } from "./packages/matt-pocock/src/workflow.ts";
        console.log(JSON.stringify({ triage: readablePhaseTitle("triage") }));
    """)
    assert result["triage"] == "Task Triage"


def test_exploration_lateral_transitions_and_bug_diagnostic_returns() -> None:
    result = run_typescript("""
        import { transitionState } from "./packages/matt-pocock/src/workflow.ts";
        const ideaResearch = {
          version: 1, workItemId: "w-1", route: "idea-to-ship",
          procedure: "research", phase: "research",
          status: "active", loadedReferences: [],
        };
        const ideaProto = transitionState(ideaResearch, "prototype");

        const protoState = {
          version: 1, workItemId: "w-1", route: "idea-to-ship",
          procedure: "prototype", phase: "prototype",
          status: "active", loadedReferences: [],
        };
        const ideaBackToResearch = transitionState(protoState, "research");

        const bugImplement = {
          version: 1, workItemId: "w-2", route: "hard-bug",
          procedure: "implement", phase: "implement",
          status: "active", loadedReferences: [],
        };
        const bugBackToDiagnosis = transitionState(bugImplement, "diagnosing-bugs");

        const archSurvey = {
          version: 1, workItemId: "w-3", route: "architecture",
          procedure: "improve-codebase-architecture", phase: "survey",
          status: "active", loadedReferences: [],
        };
        const archDesign = transitionState(archSurvey, "codebase-design");

        console.log(JSON.stringify({
          ideaProto: ideaProto.procedure,
          ideaBackToResearch: ideaBackToResearch.procedure,
          bugBackToDiagnosis: bugBackToDiagnosis.procedure,
          archDesign: archDesign.procedure,
        }));
    """)
    assert result["ideaProto"] == "prototype"
    assert result["ideaBackToResearch"] == "research"
    assert result["bugBackToDiagnosis"] == "diagnosing-bugs"
    assert result["archDesign"] == "codebase-design"


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


def test_reference_loading_keeps_external_links_verbatim() -> None:
    """Only catalogue resources rewrite; a URL is not a resource."""
    result = run_typescript("""
        import { resolveAccessibleReference } from "./packages/matt-pocock/src/resolver.ts";
        const bundle = resolveAccessibleReference("setup-matt-pocock-skills", [], "issue-tracker-gitlab");
        console.log(JSON.stringify({ content: bundle.content }));
    """)
    content = str(result["content"])
    assert "](https://gitlab.com/gitlab-org/cli)" in content
    assert "](procedure:issue-tracker-gitlab)" not in content
    assert "](../procedures/" not in content
    assert "](procedure:triage)" in content
    assert "](procedure:wayfinder)" in content


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


def test_procedure_texts_route_agents_through_the_catalog_gateway() -> None:
    catalog = json.loads((PACKAGE / "src" / "catalog.json").read_text())
    directories = {"workflow": "procedures", "utility": "procedures", "reference": "references", "asset": "assets"}
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
        lines = (PACKAGE / directories[entry["kind"]] / entry["file"]).read_text().splitlines()
        for number, line in enumerate(lines, start=1):
            for label, pattern in patterns.items():
                if pattern.search(line):
                    violations.append(f"{entry['file']}:{number}: {label}: {line.strip()}")
    assert violations == []


# ── test_procedure_delivery.py ──
"""User-invoked /matt-pocock starts render one impeccable-style block row."""


import pytest

from matt_pocock_helpers import RUNTIME_HARNESS, run_typescript


def test_a_workflow_step_does_not_re_deliver_what_is_already_in_context() -> None:
    """Re-sending a whole procedure closure every transition is what ended long tasks early."""
    result = run_typescript('''
        import { resolveProcedureDelta } from "./packages/matt-pocock/src/resolver.ts";
        const first = resolveProcedureDelta("implement", [], []);
        const repeat = resolveProcedureDelta("implement", [], first.delivered);
        const transition = resolveProcedureDelta("code-review", [], first.delivered);
        console.log(JSON.stringify({
          firstIds: first.delivered,
          firstSources: [...first.content.matchAll(/<procedure-source id="([^"]+)"/g)].map((match) => match[1]),
          repeatContent: repeat.content,
          repeatIds: repeat.delivered,
          transitionIds: transition.delivered,
          transitionSources: [...transition.content.matchAll(/<procedure-source id="([^"]+)"/g)].map((match) => match[1]),
        }));
    ''')

    # The first delivery carries the whole closure: the procedure and its dependencies.
    assert "implement" in result["firstIds"]
    assert "bdd" in result["firstIds"]
    assert result["firstSources"] == result["firstIds"]

    # Nothing new is nothing re-sent, and the delivery set does not shrink.
    assert result["repeatContent"] == ""
    assert result["repeatIds"] == result["firstIds"]

    # A transition delivers only what that procedure adds, not the shared dependencies again.
    assert "code-review" in result["transitionIds"]
    assert "code-review" in result["transitionSources"]
    assert set(result["transitionSources"]).isdisjoint(result["firstSources"])
    assert set(result["transitionSources"]) == set(result["transitionIds"]) - set(result["firstIds"])

HARNESS = RUNTIME_HARNESS + """
        const LF = String.fromCharCode(10);
        const r = runtime(["bash", "matt_pocock_workflow"]);
        const { commands, renderers, entries, userMessages } = r;
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const ctx = (choices = []) => ({ ...r.ctx, ui: {
          ...r.ctx.ui, select: async () => choices.shift(), input: async () => "",
        }});
        const command = commands.get("matt-pocock");
        const start = () => ({ messageCount: r.messages.length, userCount: userMessages.length, entryCount: entries.length });
        const snapshot = (before) => {
          const message = r.deliveries().at(-1).message;
          const rendered = renderers.get("matt-pocock-procedure")(message, { expanded: false }, theme).render(80);
          return {
            messages: r.messages.length - before.messageCount,
            userMessages: userMessages.slice(before.userCount),
            entries: entries.slice(before.entryCount),
            customType: message.customType, display: message.display, details: message.details,
            options: r.deliveries().at(-1).options, content: message.content,
            activeTools: [...r.active()],
            rows: rendered.slice(1, -1).map((row) => row.trim()),
            band: rendered,
          };
        };
"""

SCRIPT = """
        let before = start();
        await command.handler("hard-bug fix the login redirect", ctx());
        const routeTask = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("hard-bug", ctx());
        const routeOnly = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("research tighten the spacing", ctx());
        const capabilityTask = snapshot(before);

        before = start();
        await command.handler("research", ctx());
        const capabilityOnly = snapshot(before);

        before = start();
        await command.handler("", ctx(["Start a workflow", "Start an idea-to-ship flow — Shape an idea before planning and implementation."]));
        const menuRoute = snapshot(before);

        await command.handler("complete", ctx());
        before = start();
        await command.handler("", ctx(["Run a standalone capability", "Research — Primary-source research that writes a cited repository note."]));
        const menuCapability = snapshot(before);

        await command.handler("hard-bug", ctx());
        before = start();
        await command.handler("transition", ctx(["Code Review"]));
        const transition = snapshot(before);

        before = start();
        await command.handler("cancel shifting scope from the user", ctx());
        const cancelled = {
          messages: r.messages.length - before.messageCount,
          userMessages: userMessages.slice(before.userCount),
          entries: entries.slice(before.entryCount),
        };

        before = start();
        await command.handler("", ctx(["Start a task"]));
        const menuRouting = snapshot(before);

        before = start();
        await command.handler(`aaaa${LF}zzzz`, ctx());
        const freeform = snapshot(before);

        console.log(JSON.stringify({ routeTask, routeOnly, capabilityTask, capabilityOnly, menuRoute,
          menuCapability, transition, cancelled, menuRouting, freeform, activeTools: r.active() }));
"""

STATE_KEYS = ("version", "workItemId", "route", "procedure", "phase", "status", "loadedReferences", "deliveredProcedures")

LF = "\n"


def state_without_request(details: dict[str, object]) -> dict[str, object]:
    return {key: details[key] for key in STATE_KEYS}


@pytest.fixture(scope="module")
def delivery() -> dict[str, object]:
    return run_typescript(HARNESS + SCRIPT)


@pytest.mark.parametrize("name,body", [
    ("routeTask", ["fix the login redirect"]),
    ("routeOnly", ["Reproducing & Diagnostics"]),
    ("capabilityTask", ["tighten the spacing"]),
    ("capabilityOnly", ["Research"]),
    ("menuRoute", ["Shaping & Requirements"]),
    ("menuCapability", ["Research"]),
    ("transition", ["Code Review"]),
    ("menuRouting", []),
    ("freeform", ["aaaa", "zzzz"]),
])
def test_starts_deliver_one_displayed_block(delivery: dict[str, object], name: str, body: list[str]) -> None:
    item = delivery[name]
    assert item["userMessages"] == []
    assert item["messages"] == 1
    assert item["customType"] == "matt-pocock-procedure"
    assert item["display"] is True
    assert item["options"] == {"deliverAs": "followUp", "triggerTurn": True}
    assert item["rows"] == ["[matt pocock] started"] + (["", *body] if body else [])
    assert "to expand" not in "\n".join(item["band"])
    assert all(len(row) <= 80 for row in item["band"])


@pytest.mark.parametrize("name,task", [("routeTask", "fix the login redirect"), ("capabilityTask", "tighten the spacing")])
def test_a_supplied_task_reaches_prompt_and_row(delivery: dict[str, object], name: str, task: str) -> None:
    item = delivery[name]
    assert item["details"]["request"] == task
    assert f"User target/request:{LF}{task}" in item["content"]
    assert item["content"].rstrip().endswith(task) or "## Workflow state contract" in item["content"]


def test_a_supplied_task_never_enters_persisted_state(delivery: dict[str, object]) -> None:
    route_task = delivery["routeTask"]
    assert [entry["customType"] for entry in route_task["entries"]] == ["matt-pocock-workflow"]
    record = route_task["entries"][0]["data"]
    assert record == state_without_request(route_task["details"])
    assert "request" not in record
    assert delivery["capabilityTask"]["entries"] == []


def test_freeform_routing_keeps_the_request_and_starts_no_workflow(delivery: dict[str, object]) -> None:
    freeform = delivery["freeform"]
    assert freeform["details"] == {"request": f"aaaa{LF}zzzz"}
    assert freeform["entries"] == []
    assert "Route and execute this request" in freeform["content"]
    assert f"aaaa{LF}zzzz" in freeform["content"]


def test_menu_routing_rows_stay_head_only_and_start_no_workflow(delivery: dict[str, object]) -> None:
    routing = delivery["menuRouting"]
    assert routing["details"] == {"request": ""}
    assert routing["entries"] == []
    assert "recent conversation context" in routing["content"]


def test_workflow_starts_activate_active_tools(delivery: dict[str, object]) -> None:
    assert "matt_pocock_active" in delivery["routeTask"]["activeTools"]
    assert "matt_pocock_ask" in delivery["routeTask"]["activeTools"]


def test_the_cancel_reason_comes_from_the_command_input(delivery: dict[str, object]) -> None:
    cancelled = delivery["cancelled"]
    assert cancelled["messages"] == 0
    assert cancelled["userMessages"] == []
    assert [entry["customType"] for entry in cancelled["entries"]] == ["matt-pocock-workflow"]
    terminal = cancelled["entries"][0]["data"]
    assert terminal["status"] == "cancelled"
    assert terminal["reason"] == "shifting scope from the user"


# ── test_glossary_compatibility.py ──
"""The upstream glossary rename preserves references stored by earlier sessions."""
from matt_pocock_helpers import run_typescript


def test_previous_context_format_id_restores_the_new_glossary_reference() -> None:
    result = run_typescript('''
        import { resolveWorkflowContext, resolveAccessibleReference } from "./packages/matt-pocock/src/resolver.ts";
        const restored = resolveWorkflowContext("improve-codebase-architecture", ["domain-modeling", "CONTEXT-FORMAT"]);
        const oldReference = resolveAccessibleReference("domain-modeling", [], "CONTEXT-FORMAT");
        const newReference = resolveAccessibleReference("domain-modeling", [], "GLOSSARY-FORMAT");
        console.log(JSON.stringify({ restored, oldReference, newReference }));
    ''')
    assert result["oldReference"] == result["newReference"]
    assert "GLOSSARY-FORMAT" in result["restored"]["loaded"]
    assert 'source="procedure/GLOSSARY-FORMAT"' in result["restored"]["content"]


# ── test_writing_for_agents.py ──
from matt_pocock_helpers import run_typescript


def test_writing_capability_includes_model_aware_authoring_guidance() -> None:
    result = run_typescript("""
        import { resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        console.log(JSON.stringify(resolveProcedureBundle("writing-for-agents")));
    """)
    text = result["content"]
    for guidance in (
        "Rethinking skills and prompts for GPT-6 Astra",
        "adding or changing a migration, or reviewing its rollout",
        "minimal router",
        "architecture.md for service boundaries",
        "models used by contributors",
        "disposable fixtures and have no production access",
        "production writes, destructive operations, and external publication",
        "running it, inspecting the result, fixing failures",
        "exploration scope and stopping condition",
    ):
        assert guidance in text, f"Missing authoring guidance: {guidance}"


# ── test_sync_checker.py ──
"""Revision roles may coincide; comparison fixtures never mutate workspace metadata."""

import json
import subprocess
from pathlib import Path

import pytest

from matt_pocock_helpers import PACKAGE


@pytest.mark.parametrize("coincident", [False, True])
def test_checker_reads_isolated_metadata_with_truthful_revision_roles(tmp_path: Path, coincident: bool) -> None:
    source = PACKAGE / "upstream" / "upstream-selection.json"
    original = source.read_bytes()
    metadata = json.loads(original)
    if coincident:
        metadata["comparedCommit"] = metadata["latestCheckedCommit"]
        metadata["resolvedTagCommit"] = metadata["latestCheckedCommit"]
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(metadata))
    result = subprocess.run(
        ["node", str(PACKAGE / "upstream/check-upstream-sync.mjs"), "--selection", str(selection)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True
    assert source.read_bytes() == original


def test_checker_rejects_duplicate_options() -> None:
    result = subprocess.run(
        ["node", str(PACKAGE / "upstream/check-upstream-sync.mjs"), "--selection", "a", "--selection", "b"],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 1
    assert "usage:" in result.stderr


# ── test_upstream_sync.py ──

import json
import re
import subprocess
import tarfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
CHECKER = PACKAGE / "upstream" / "check-upstream-sync.mjs"
SELECTION = PACKAGE / "upstream" / "upstream-selection.json"


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(CHECKER), *args],
        cwd=PACKAGE,
        text=True,
        capture_output=True,
    )


def test_selection_records_upstream_revision_roles_and_complete_reasons() -> None:
    metadata = json.loads(SELECTION.read_text())
    for field in ("comparedCommit", "resolvedTagCommit", "latestCheckedCommit"):
        assert re.fullmatch(r"[0-9a-f]{40}", metadata[field])
    assert re.fullmatch(r"v\d+\.\d+\.\d+", metadata["comparisonTag"])
    assert all(item["localCatalogId"] for item in metadata["selected"])
    assert all(item["reason"].strip() for item in metadata["excluded"])
    selected = {item["upstreamSkill"] for item in metadata["selected"]}
    excluded = {item["upstreamSkill"]: item["reason"] for item in metadata["excluded"]}
    assert {"pr", "retro"} <= selected
    assert "implement-spec" in excluded
    assert "Pi v1" in excluded["implement-spec"]
    assert "resolving-merge-conflicts" not in selected | set(excluded)


def test_checker_validates_local_selection_without_network() -> None:
    result = run_checker()
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["upstreamCompared"] is False
    assert report["selected"] > 0
    assert report["excluded"] > 0


def test_packed_package_includes_sync_metadata_and_checker(packed_package: Path) -> None:
    with tarfile.open(packed_package) as archive:
        names = set(archive.getnames())
    assert {
        "package/upstream/UPSTREAM.md", "package/upstream/upstream-selection.json",
        "package/upstream/check-upstream-sync.mjs",
    } <= names


def git(upstream: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(upstream), *args], text=True).strip()


def write_upstream_fixture(upstream: Path, metadata: dict[str, object]) -> None:
    subprocess.check_call(["git", "init", "-q", str(upstream)])
    subprocess.check_call(["git", "-C", str(upstream), "config", "user.email", "fixture@example.com"])
    subprocess.check_call(["git", "-C", str(upstream), "config", "user.name", "Fixture"])

    for item in metadata["selected"]:
        source = upstream / item["upstreamPath"]
        source.parent.mkdir(parents=True, exist_ok=True)
        local_body = (PACKAGE / item["localResource"]).read_text()
        disabled = "disable-model-invocation: true\n" if item["upstreamInvocation"] == "user" else ""
        source.write_text(
            f"---\nname: {item['upstreamSkill']}\n{disabled}---\n\n{local_body}"
        )

    for item in metadata["excluded"]:
        source = upstream / item["upstreamPath"]
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"---\nname: {item['upstreamSkill']}\n---\n\nExcluded fixture.\n")

    subprocess.check_call(["git", "-C", str(upstream), "add", "."])
    subprocess.check_call(["git", "-C", str(upstream), "commit", "-qm", "fixture"])
    metadata["comparedCommit"] = git(upstream, "rev-parse", "HEAD")
    subprocess.check_call(["git", "-C", str(upstream), "commit", "--allow-empty", "-qm", "tag target"])
    metadata["resolvedTagCommit"] = git(upstream, "rev-parse", "HEAD")
    subprocess.check_call([
        "git", "-C", str(upstream), "update-ref",
        f"refs/tags/{metadata['comparisonTag']}", metadata["resolvedTagCommit"],
    ])
    subprocess.check_call(["git", "-C", str(upstream), "commit", "--allow-empty", "-qm", "latest"])
    metadata["latestCheckedCommit"] = git(upstream, "rev-parse", "HEAD")


def test_checker_compares_an_already_cloned_upstream_tree(tmp_path: Path) -> None:
    metadata = json.loads(SELECTION.read_text())
    upstream = tmp_path / "skills"
    write_upstream_fixture(upstream, metadata)
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(metadata))
    result = run_checker("--selection", str(selection), "--upstream", str(upstream))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["upstreamCompared"] is True
    assert report["upstreamSkills"] == len(metadata["selected"]) + len(metadata["excluded"])
    assert report["content"]["exact"] == len(metadata["selected"])
    assert report["content"]["adapted"] == 0


def test_selection_classifies_new_in_progress_upstream_skill() -> None:
    metadata = json.loads(SELECTION.read_text())
    excluded = {item["upstreamSkill"]: item for item in metadata["excluded"]}
    assert "software-factory" in excluded
    entry = excluded["software-factory"]
    assert entry["upstreamPath"] == "skills/in-progress/software-factory/SKILL.md"
    assert "Pi v1" in entry["reason"]
    assert "factory" in entry["reason"].lower()


def test_checker_rejects_an_unclassified_upstream_skill(tmp_path: Path) -> None:
    metadata = json.loads(SELECTION.read_text())
    upstream = tmp_path / "skills"
    write_upstream_fixture(upstream, metadata)
    extra = upstream / "skills" / "in-progress" / "unclassified-skill" / "SKILL.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("---\nname: unclassified-skill\n---\n\nUnclassified fixture.\n")
    subprocess.check_call(["git", "-C", str(upstream), "add", "."])
    subprocess.check_call(["git", "-C", str(upstream), "commit", "-qm", "unclassified skill"])
    metadata["latestCheckedCommit"] = git(upstream, "rev-parse", "HEAD")
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(metadata))
    result = run_checker("--selection", str(selection), "--upstream", str(upstream))
    assert result.returncode == 1
    assert "unclassified upstream skills" in result.stderr


def test_checker_rejects_upstream_checkout_at_a_different_head(tmp_path: Path) -> None:
    metadata = json.loads(SELECTION.read_text())
    upstream = tmp_path / "skills"
    write_upstream_fixture(upstream, metadata)
    metadata["latestCheckedCommit"] = "0" * 40
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps(metadata))
    result = run_checker("--selection", str(selection), "--upstream", str(upstream))
    assert result.returncode == 1
    assert "metadata latestCheckedCommit" in result.stderr
