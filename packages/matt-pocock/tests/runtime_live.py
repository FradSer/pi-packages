"""Pi 1.0 runtime matrix for the matt-pocock extension.

The provider is local and deterministic; Pi's extension loader, agent loop,
schema validation, persistence, active-tool loadout and lifecycle events remain
real. This deliberately uses a temporary HOME and never reads user auth.
"""

from __future__ import annotations

import json
import os
import pty
import select
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from live_pty import base_env

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name("runtime-live-fixture.ts")


def call(name: str, **arguments: object) -> dict[str, object]:
    return {"name": name, "arguments": arguments}


def catalog_inventory() -> tuple[dict[str, tuple[str, list[tuple[str, str]]]], list[str], list[str], tuple[str, list[str]]]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    routes: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    for definition in catalog:
        for placement in definition.get("workflows", []):
            route = placement["route"]
            entry = definition["id"] if placement.get("entry") else routes.get(route, ("", []))[0]
            edges = routes.get(route, (entry, []))[1]
            edges.extend((definition["id"], target) for target in placement.get("allowedNext", []))
            routes[route] = (entry, edges)
    model = [definition["id"] for definition in catalog
             if definition.get("standalone") and definition.get("invocation") == "model"]
    user = [definition["id"] for definition in catalog
            if definition.get("standalone") and definition.get("invocation") == "user"]
    references = next((definition for definition in catalog
                       if definition.get("standalone") and definition.get("discloses")), None)
    assert references, "catalog must retain at least one disclosed standalone reference"
    return routes, model, user, (references["id"], references["discloses"])


def catalog_phases() -> dict[tuple[str, str], str]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    return {(placement["route"], definition["id"]): placement["phase"]
            for definition in catalog for placement in definition.get("workflows", [])}


def model_disclosures() -> list[tuple[str, list[str]]]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    return [(definition["id"], definition["discloses"])
            for definition in catalog
            if definition.get("standalone") and definition.get("invocation") == "model"
            and definition.get("discloses")]


def catalog_definitions() -> dict[str, dict[str, object]]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    return {definition["id"]: definition for definition in catalog}


def catalog_aliases() -> dict[str, str]:
    definitions = catalog_definitions()
    return {alias: identifier for identifier, definition in definitions.items()
            for alias in definition.get("aliases", [])}


def required_closure(identifier: str, definitions: dict[str, dict[str, object]], seen: set[str] | None = None) -> set[str]:
    visited = set() if seen is None else seen
    if identifier in visited:
        return visited
    visited.add(identifier)
    for dependency in definitions[identifier].get("requires", []):
        required_closure(dependency, definitions, visited)
    return visited


def standalone_disclosure_paths() -> list[dict[str, object]]:
    """Return bounded fresh-root paths for every standalone/reference target."""
    definitions = catalog_definitions()
    aliases = catalog_aliases()
    cases: list[dict[str, object]] = []
    alias_used = False
    for root, definition in definitions.items():
        if not definition.get("standalone"):
            continue
        pending: list[tuple[str, str | None]] = []
        loaded_closure = required_closure(root, definitions)
        for dependency in loaded_closure:
            pending.extend((reference, None) for reference in definitions[dependency].get("discloses", []))
        parent: dict[str, str | None] = {}
        queued: set[str] = set()
        while pending:
            raw, parent_id = pending.pop(0)
            canonical = aliases.get(raw, raw)
            if canonical in loaded_closure:
                continue
            if canonical in parent:
                continue
            parent[canonical] = parent_id
            for child in definitions[canonical].get("discloses", []):
                child = aliases.get(child, child)
                if child not in loaded_closure and child not in parent and child not in queued:
                    queued.add(child)
                    pending.append((child, canonical))
        targets: list[str | None] = []
        for candidate in parent:
            canonical_chain: list[str] = []
            cursor = candidate
            while cursor is not None:
                canonical_chain.append(cursor)
                cursor = parent[cursor]
            canonical_chain.reverse()
            loaded = set(loaded_closure)
            valid = True
            for reference in canonical_chain:
                if reference in loaded:
                    valid = False
                    break
                loaded.update(required_closure(reference, definitions))
            if valid:
                targets.append(candidate)
        if not targets:
            targets = [None]
        for target in targets:
            canonical_chain: list[str] = []
            cursor = target
            while cursor is not None:
                canonical_chain.append(cursor)
                cursor = parent[cursor]
            canonical_chain.reverse()
            references: list[tuple[str, str]] = []
            for canonical in canonical_chain:
                requested = canonical
                if canonical == "GLOSSARY-FORMAT" and not alias_used:
                    requested = "CONTEXT-FORMAT"
                    alias_used = True
                references.append((requested, canonical))
            calls: list[dict[str, object]] = [call("matt_pocock_workflow", mode="capability", capability=root)]
            calls.extend(call("matt_pocock_workflow", mode="reference", capability=root, reference=requested)
                         for requested, _canonical in references)
            cases.append({"root": root, "invocation": definition["invocation"], "references": references,
                          "target": target, "calls": calls})
    return cases


def workflow_reference_cases() -> list[dict[str, object]]:
    """Create one fresh-route case for each placement/reference pair."""
    definitions = catalog_definitions()
    routes, _model, _user, _references = catalog_inventory()
    cases: list[dict[str, object]] = []
    for route, (entry, edges) in routes.items():
        graph: dict[str, list[str]] = {}
        for source, target in edges:
            graph.setdefault(source, []).append(target)
        paths: dict[str, list[str]] = {entry: []}
        queue: list[tuple[str, list[str]]] = [(entry, [])]
        while queue:
            source, path = queue.pop(0)
            for target in graph.get(source, []):
                if target not in paths:
                    paths[target] = [*path, target]
                    queue.append((target, paths[target]))
        for procedure, definition in definitions.items():
            placement = next((candidate for candidate in definition.get("workflows", [])
                              if candidate["route"] == route), None)
            if placement is None:
                continue
            references = definition.get("discloses", [])
            assert procedure in paths, (route, procedure, entry)
            if not references:
                calls = [call("matt_pocock_workflow", mode="workflow", route=route)]
                calls.extend(call("matt_pocock_active", action="transition", target=target)
                             for target in paths[procedure])
                calls.append(call("matt_pocock_active", action="complete"))
                cases.append({"route": route, "procedure": procedure, "reference": None, "calls": calls})
                continue
            for reference in references:
                calls = [call("matt_pocock_workflow", mode="workflow", route=route)]
                calls.extend(call("matt_pocock_active", action="transition", target=target)
                             for target in paths[procedure])
                calls.extend([call("matt_pocock_active", action="load", reference=reference),
                              call("matt_pocock_active", action="cancel", reason="reference coverage")])
                cases.append({"route": route, "procedure": procedure, "reference": reference,
                              "calls": calls})
    return cases


def procedure_closure(ids: list[str]) -> set[str]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    definitions = {definition["id"]: definition for definition in catalog}
    result: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in result:
            return
        result.add(identifier)
        for dependency in definitions[identifier].get("requires", []):
            visit(dependency)

    for identifier in ids:
        visit(identifier)
    return result


def restart_case() -> tuple[str, str, str]:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    definitions = {definition["id"]: definition for definition in catalog}

    def closure(identifier: str) -> set[str]:
        result: set[str] = set()

        def visit(current: str) -> None:
            if current in result:
                return
            result.add(current)
            for dependency in definitions[current].get("requires", []):
                visit(dependency)

        visit(identifier)
        return result

    for definition in catalog:
        for placement in definition.get("workflows", []):
            if not placement.get("entry"):
                continue
            disclosures = set().union(*(definitions[item].get("discloses", []) for item in closure(definition["id"])))
            if "GLOSSARY-FORMAT" in disclosures:
                return placement["route"], definition["id"], "GLOSSARY-FORMAT"
    raise AssertionError("catalog needs an entry whose dependency closure discloses GLOSSARY-FORMAT")


def route_entry(route: str) -> str:
    catalog = json.loads((ROOT / "packages/matt-pocock/src/catalog.json").read_text())
    for definition in catalog:
        if any(placement.get("route") == route and placement.get("entry")
               for placement in definition.get("workflows", [])):
            return definition["id"]
    raise AssertionError(f"catalog has no entry for {route}")


def matrix_calls() -> list[dict[str, object]]:
    routes, model_capabilities, user_capabilities, (reference_capability, references) = catalog_inventory()
    calls: list[dict[str, object]] = []
    for route, (entry, edges) in routes.items():
        calls.extend([call("matt_pocock_workflow", mode="workflow", route=route),
                      call("matt_pocock_active", action="complete")])
        for source, target in edges:
            # Start each edge from a fresh workflow, walking a shortest valid
            # path to its source first. This keeps every assertion a valid host
            # execution while still giving every catalog edge a real Pi call.
            graph: dict[str, list[str]] = {}
            for left, right in edges:
                graph.setdefault(left, []).append(right)
            queue: list[tuple[str, list[str]]] = [(entry, [])]
            paths: dict[str, list[str]] = {entry: []}
            while queue:
                current, path = queue.pop(0)
                for next_node in graph.get(current, []):
                    if next_node not in paths:
                        paths[next_node] = [*path, next_node]
                        queue.append((next_node, paths[next_node]))
            assert source in paths, (route, source, entry)
            targets = [*paths[source], target]
            calls.append(call("matt_pocock_workflow", mode="workflow", route=route))
            calls.extend(call("matt_pocock_active", action="transition", target=next_node) for next_node in targets)
            calls.append(call("matt_pocock_active", action="complete"))
    calls.extend([
        call("matt_pocock_workflow", mode="workflow", route=next(iter(routes))),
        call("matt_pocock_active", action="cancel", reason="runtime matrix cancellation"),
        call("matt_pocock_workflow", mode="workflow", route=next(iter(routes))),
        call("matt_pocock_active", action="transition", target="__invalid_transition__"),
        call("matt_pocock_active", action="cancel", reason="invalid transition checked"),
        call("matt_pocock_workflow", mode="workflow", route=next(iter(routes))),
        call("matt_pocock_active", action="load", reference="__not_disclosed__"),
        call("matt_pocock_active", action="cancel", reason="invalid reference checked"),
    ])
    for capability in model_capabilities:
        calls.append(call("matt_pocock_workflow", mode="capability", capability=capability))
    # Every user-invoked capability gets a real Pi call too. Without these the
    # matrix proved nothing about the path that answers "grill me".
    for capability in user_capabilities:
        calls.append(call("matt_pocock_workflow", mode="user-capability", capability=capability))
    calls.append(call("matt_pocock_workflow", mode="capability", capability=user_capabilities[0]))
    calls.extend(call("matt_pocock_workflow", mode="capability", capability=capability)
                 for capability, _references in model_disclosures()
                 if capability not in model_capabilities)
    for capability, disclosed in model_disclosures():
        calls.extend(call("matt_pocock_workflow", mode="reference", capability=capability, reference=reference)
                     for reference in disclosed)
    calls.append(call("matt_pocock_workflow", mode="reference", capability=reference_capability,
                      reference="__not_disclosed__"))
    return calls


def isolated_env(root: Path, evidence: Path, calls: list[dict[str, object]]) -> dict[str, str]:
    agent = root / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    # Keep the compact probe small and deterministic: Pi's default 20k recent
    # token floor would require a large synthetic transcript before the native
    # manual boundary can be reached.
    (agent / "settings.json").write_text(json.dumps({"theme": "dark", "quietStartup": True,
                                                     "compaction": {"enabled": True, "reserveTokens": 1,
                                                                     "keepRecentTokens": 1}}))
    env = base_env()
    env.update({"HOME": str(root), "PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1",
                "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "off", "PI_RUNTIME_AUTH": "local-only",
                "PI_RUNTIME_EVIDENCE": str(evidence), "PI_RUNTIME_CALLS": json.dumps(calls), "TERM": "xterm-256color"})
    return env


def command(pi: str, *, mode: str | None = "text", session: Path | None = None) -> list[str]:
    result = [pi, "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
              "--no-context-files", "--no-approve", "--extension", str(FIXTURE), "--provider",
              "matt-pocock-runtime-matrix", "--model", "deterministic", "--thinking", "off",
              "--no-builtin-tools"]
    if mode is not None:
        result.extend(["--mode", mode])
    if session:
        result.extend(["--session", str(session)])
    return result


def read_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run_matrix(pi: str, root: Path) -> None:
    _routes, _model_capabilities, user_capabilities, _disclosures = catalog_inventory()
    evidence = root / "matrix.jsonl"
    expected = matrix_calls()
    env = isolated_env(root, evidence, expected)
    result = subprocess.run([*command(pi), "--print", "Run the complete Matt Pocock runtime matrix"],
                            cwd=root, env=env, input="", text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MP_RUNTIME_READY" in result.stdout, result.stdout + result.stderr
    rows = read_rows(evidence)
    results = [row for row in rows if row["kind"] == "tool_result"]
    assert len(results) == len(expected), (len(results), len(expected), result.stdout, result.stderr)
    phases = catalog_phases()
    for index, (request, result_row) in enumerate(zip(expected, results, strict=True)):
        arguments = request["arguments"]
        assert result_row["tool"] == request["name"], (index, request, result_row)
        details = result_row["details"]
        assert isinstance(details, dict), (index, result_row)
        if result_row["isError"]:
            assert ((request["name"] == "matt_pocock_active"
                     and request["arguments"].get("action") in ("transition", "load"))
                    or (request["name"] == "matt_pocock_workflow"
                        and request["arguments"].get("mode") == "reference")
                    or (request["name"] == "matt_pocock_workflow"
                        and request["arguments"].get("mode") == "capability"
                        and request["arguments"].get("capability") == user_capabilities[0])), (index, request, result_row)
            continue
        if request["name"] == "matt_pocock_workflow":
            assert details.get("mode") == arguments["mode"], (index, request, result_row)
            if arguments["mode"] == "workflow":
                assert details.get("route") == arguments["route"] and details.get("status") == "active", (index, request, result_row)
                assert details.get("phase") == phases[(arguments["route"], details["procedure"])], (index, request, result_row)
            elif arguments["mode"] in ("capability", "user-capability"):
                assert details.get("mode") == arguments["mode"], (index, request, result_row)
                assert details.get("capability") == arguments["capability"], (index, request, result_row)
            else:
                assert details.get("capability") == arguments["capability"]
                assert details.get("reference") == arguments["reference"]
        elif arguments["action"] == "transition" and not result_row["isError"]:
            state = details.get("state")
            assert isinstance(state, dict), (index, request, result_row)
            assert details.get("action") == "transition" and state.get("status") == "active", (index, request, result_row)
            assert state.get("procedure") == arguments["target"]
            assert state.get("phase") == phases[(state["route"], arguments["target"])]
        elif arguments["action"] in ("complete", "cancel") and not result_row["isError"]:
            state = details.get("state")
            assert isinstance(state, dict), (index, request, result_row)
            assert details.get("action") == arguments["action"]
            assert state.get("status") == ("completed" if arguments["action"] == "complete" else "cancelled"), (index, request, result_row)
            assert "matt_pocock_active" not in result_row["activeTools"] and "matt_pocock_ask" not in result_row["activeTools"], (index, request, result_row)
    errors = [row for row in results if row["isError"]]
    assert len(errors) == 4, errors
    assert {row["tool"] for row in errors} == {"matt_pocock_active", "matt_pocock_workflow"}, errors
    registered = next(row for row in rows if row["kind"] == "session_start")
    assert set(["matt_pocock_workflow", "matt_pocock_active", "matt_pocock_ask"]).issubset(registered["tools"])
    assert "matt_pocock_workflow" in registered["activeTools"]
    active_rows = [row for row in results if "matt_pocock_active" in row["activeTools"]]
    assert active_rows, "the active tool was never enabled in the real Pi loadout"
    assert any("matt_pocock_active" not in row["activeTools"] for row in results), "active tools never cleared"
    invalid_indexes = [index for index, request in enumerate(expected)
                       if (request["name"] == "matt_pocock_active"
                           and ((request["arguments"].get("action") == "transition"
                                 and request["arguments"].get("target") == "__invalid_transition__")
                                or (request["arguments"].get("action") == "load"
                                    and request["arguments"].get("reference") == "__not_disclosed__")))]
    for index in invalid_indexes:
        row = results[index]
        assert row["isError"] and row["appendCount"] == results[index - 1]["appendCount"], (index, row)
        previous_state = next((previous["details"] for previous in reversed(results[:index])
                               if isinstance(previous["details"], dict)
                               and previous["details"].get("status") == "active"), None)
        assert previous_state, (index, rows[:index])
        assert row["activeTools"] == results[index - 1]["activeTools"], (index, row)
        terminal = results[index + 1]["details"].get("state", {})
        assert isinstance(terminal, dict) and terminal.get("status") == "cancelled"
        assert terminal.get("workItemId") == previous_state.get("workItemId")
        assert terminal.get("route") == previous_state.get("route")
        assert terminal.get("procedure") == previous_state.get("procedure")
    print(f"matrix: {len(results)} real tool executions, {len(errors)} expected rejection cases")


def session_tool_result_texts(path: Path) -> list[str]:
    assert path.exists(), f"Pi did not persist the coverage session: {path}"
    texts: list[str] = []
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        message = entry.get("message", {})
        if not isinstance(message, dict) or message.get("role") != "toolResult":
            continue
        content = message.get("content", [])
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.append("\n".join(part.get("text", "") for part in content
                                    if isinstance(part, dict) and isinstance(part.get("text"), str)))
    return texts


def assert_persisted_sources(path: Path, canonical_ids: list[str]) -> None:
    texts = session_tool_result_texts(path)
    cursor = 0
    for canonical in canonical_ids:
        while cursor < len(texts) and f'<procedure-source id="{canonical}"' not in texts[cursor]:
            cursor += 1
        assert cursor < len(texts), {"canonical": canonical, "toolResults": texts}
        cursor += 1


def run_reference_case(pi: str, root: Path, case_number: int, case: dict[str, object]) -> None:
    case_root = root / f"reference-case-{case_number:03d}"
    case_root.mkdir(parents=True, exist_ok=True)
    evidence = case_root / "reference.jsonl"
    calls = case["calls"]
    assert isinstance(calls, list)
    env = isolated_env(case_root, evidence, calls)
    session = case_root / "reference-session.jsonl"
    result = subprocess.run([*command(pi, session=session), "--print", f"Run reference coverage case {case_number}"],
                            cwd=case_root, env=env, input="", text=True,
                            capture_output=True, timeout=120)
    assert result.returncode == 0, {"case": case, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    assert "MP_RUNTIME_READY" in result.stdout, {"case": case, "stdout": result.stdout[-4000:]}
    rows = read_rows(evidence)
    results = [row for row in rows if row.get("kind") == "tool_result"]
    assert len(results) == len(calls), (case, len(results), len(calls), rows)
    positions = [index for index, row in enumerate(rows) if row.get("kind") == "tool_result"]
    previous_append = 0
    expected_sources: list[str] = []
    for index, (request, row, position) in enumerate(zip(calls, results, positions, strict=True)):
        assert row["tool"] == request["name"], (case, index, request, row)
        arguments = request["arguments"]
        details = row.get("details")
        assert isinstance(details, dict), (case, index, row)
        if row["isError"]:
            assert (case.get("invocation") == "user" and index == 0), (case, index, row)
            assert arguments.get("mode") == "capability", (case, index, row)
            assert row.get("appendCount") == previous_append, (case, index, row)
            if index:
                assert row.get("activeTools") == results[index - 1].get("activeTools", row.get("activeTools")), (case, index, row)
            continue
        assert row.get("appendCount") == previous_append, (case, index, row)
        assert "matt_pocock_active" not in row.get("activeTools", []), (case, index, row)
        if arguments.get("mode") == "capability":
            assert details == {"mode": "capability", "capability": arguments["capability"]}, (case, index, row)
        else:
            assert arguments.get("mode") == "reference"
            assert details.get("mode") == "reference"
            assert details.get("capability") == arguments["capability"]
            assert details.get("reference") == arguments["reference"]
            canonical = next(canonical for requested, canonical in case.get("references", [])
                             if requested == arguments["reference"])
            expected_sources.append(canonical)
        previous_append = row.get("appendCount", previous_append)
    assert_persisted_sources(session, expected_sources)


def run_workflow_reference_case(pi: str, root: Path, case_number: int, case: dict[str, object]) -> None:
    case_root = root / f"workflow-reference-case-{case_number:03d}"
    case_root.mkdir(parents=True, exist_ok=True)
    evidence = case_root / "reference.jsonl"
    calls = case["calls"]
    assert isinstance(calls, list)
    env = isolated_env(case_root, evidence, calls)
    session = case_root / "reference-session.jsonl"
    result = subprocess.run([*command(pi, session=session), "--print", f"Run workflow reference case {case_number}"],
                            cwd=case_root, env=env, input="", text=True,
                            capture_output=True, timeout=120)
    assert result.returncode == 0, {"case": case, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    assert "MP_RUNTIME_READY" in result.stdout, {"case": case, "stdout": result.stdout[-4000:]}
    rows = read_rows(evidence)
    results = [row for row in rows if row.get("kind") == "tool_result"]
    assert len(results) == len(calls), (case, len(results), len(calls), rows)
    positions = [index for index, row in enumerate(rows) if row.get("kind") == "tool_result"]
    load_seen = False
    expected_sources: list[str] = []
    for request, row, position in zip(calls, results, positions, strict=True):
        assert not row["isError"], (case, request, row)
        assert row["tool"] == request["name"], (case, request, row)
        details = row.get("details")
        assert isinstance(details, dict), (case, row)
        action = request["arguments"].get("action")
        if action == "load":
            load_seen = True
            assert details.get("action") == "load", (case, row)
            state = details.get("state")
            assert isinstance(state, dict), (case, row)
            assert request["arguments"]["reference"] in state.get("loadedReferences", []), (case, row)
            expected_sources.append(request["arguments"]["reference"])
        elif action == "cancel":
            assert details.get("action") == "cancel", (case, row)
            assert details.get("state", {}).get("status") == "cancelled", (case, row)
    if case.get("reference") is None:
        assert not load_seen, case
    else:
        assert load_seen, case
    assert_persisted_sources(session, expected_sources)


def run_reference_coverage(pi: str, root: Path) -> None:
    standalone = standalone_disclosure_paths()
    standalone_roots = {case["root"] for case in standalone}
    user_only_roots = {case["root"] for case in standalone if case["invocation"] == "user"}
    assert len(standalone_roots) == 21, standalone
    assert len(user_only_roots) == 8
    for index, case in enumerate(standalone, start=1):
        run_reference_case(pi, root, index, case)

    workflow_cases = workflow_reference_cases()
    placement_count = sum(len(definition.get("workflows", [])) for definition in catalog_definitions().values())
    assert placement_count == 28
    for index, case in enumerate(workflow_cases, start=1):
        run_workflow_reference_case(pi, root, index, case)
    print(json.dumps({"standaloneRoots": len(standalone_roots),
                      "userOnlyRoots": len(user_only_roots),
                      "standaloneReferencePaths": len(standalone),
                      "standaloneReferenceLoads": sum(len(case["references"]) for case in standalone),
                      "workflowPlacements": placement_count,
                      "workflowPlacementCases": len(workflow_cases),
                      "workflowReferenceCases": sum(case["reference"] is not None for case in workflow_cases)}))


def run_restart(pi: str, root: Path) -> None:
    session = root / "restart.jsonl"
    evidence = root / "restart.jsonl.evidence"
    route, entry, reference = restart_case()
    env = isolated_env(root, evidence, [call("matt_pocock_workflow", mode="workflow", route=route),
                                        call("matt_pocock_active", action="load", reference=reference)])
    first = subprocess.run([*command(pi, session=session), "--print", "Start a workflow for restart verification"],
                           cwd=root, env=env, input="", text=True, capture_output=True, timeout=60)
    assert first.returncode == 0, first.stdout + first.stderr
    assert session.exists(), "Pi did not persist the session used for restore verification"
    legacy_lines = []
    replaced_legacy_reference = False
    for line in session.read_text().splitlines():
        session_entry = json.loads(line)
        if (session_entry.get("type") == "custom" and session_entry.get("customType") == "matt-pocock-workflow"
                and isinstance(session_entry.get("data"), dict)
                and "GLOSSARY-FORMAT" in session_entry["data"].get("loadedReferences", [])):
            session_entry["data"]["loadedReferences"] = ["CONTEXT-FORMAT" if reference == "GLOSSARY-FORMAT" else reference
                                                            for reference in session_entry["data"]["loadedReferences"]]
            replaced_legacy_reference = True
        legacy_lines.append(json.dumps(session_entry))
    assert replaced_legacy_reference, "restart fixture did not find the persisted GLOSSARY-FORMAT state"
    session.write_text("\n".join(legacy_lines) + "\n")
    before_restore = len(read_rows(evidence))
    env["PI_RUNTIME_CALLS"] = json.dumps([call("matt_pocock_active", action="complete")])
    env["PI_RUNTIME_RESULT_OFFSET"] = "2"
    second = subprocess.run([*command(pi, session=session), "--print", "Complete the restored workflow"],
                            cwd=root, env=env, input="", text=True, capture_output=True, timeout=60)
    assert second.returncode == 0, second.stdout + second.stderr
    rows = read_rows(evidence)
    starts = [row for row in rows if row["kind"] == "session_start"]
    assert len(starts) >= 2, rows
    assert any(row["reason"] in ("reload", "startup") for row in starts[1:]), starts
    restored = [row for row in rows[before_restore:] if row["kind"] == "procedure" and row["display"] is False]
    assert restored, "restart did not deliver the active workflow into the real Pi context"
    loaded = [row for row in rows if row["kind"] == "tool_result"
              and row["details"].get("action") == "load"]
    assert loaded and reference in loaded[-1]["details"].get("state", {}).get("loadedReferences", []), rows
    expected_source_ids = procedure_closure([entry, reference])
    assert any(row["kind"] == "model_context" and row["procedureSourceComplete"]
               and row["procedureSourceBytes"] > 100
               and expected_source_ids.issubset(set(row["procedureSourceIds"]))
               for row in rows[before_restore:]), rows
    assert any(row["kind"] == "tool_result" and row["details"].get("state", {}).get("status") == "completed" for row in rows), rows
    print("restart: persisted active workflow restored and completed in a second real Pi process")


def run_user_commands(pi: str, root: Path) -> None:
    # A separate TUI run exercises command/user invocation. The provider emits
    # one deterministic answer per prompt; command delivery itself is native.
    # Synchronize from the fixture's session/agent events and evidence file.
    # TUI output is redraw-heavy and may contain an old model marker, so it is
    # only drained to keep the PTY responsive and is never used as a turn cue.
    evidence = root / "user.jsonl"
    env = isolated_env(root, evidence, [])
    routes, model_capabilities, user_only_capabilities, _references = catalog_inventory()
    user_capabilities = [*model_capabilities, *user_only_capabilities]
    run_results: list[dict[str, object]] = []

    def run_one(text: str) -> dict[str, object]:
        before_start = len(read_rows(evidence))
        master, slave = pty.openpty()
        proc = subprocess.Popen([*command(pi, mode=None), "--no-session", "User command runtime matrix"],
                                cwd=root, env=env, stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        transcript = bytearray()

        def drain() -> None:
            ready, _, _ = select.select([master], [], [], 0.05)
            if not ready:
                return
            try:
                chunk = os.read(master, 65536)
                if chunk:
                    transcript.extend(chunk)
            except OSError:
                return

        def wait_for_evidence(kind: str, baseline: int, timeout: float) -> list[dict[str, object]]:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                drain()
                rows = read_rows(evidence)
                if any(row.get("pid") == proc.pid and row.get("kind") == kind
                       for row in rows[baseline:]):
                    return rows
                if proc.poll() is not None:
                    raise AssertionError({"command": text, "pid": proc.pid, "stage": kind,
                                          "exitCode": proc.returncode,
                                          "evidence": rows[baseline:],
                                          "transcript": transcript.decode(errors="replace")[-4000:]})
            rows = read_rows(evidence)
            raise AssertionError({"command": text, "pid": proc.pid, "stage": kind,
                                  "exitCode": proc.poll(),
                                  "evidence": rows[baseline:],
                                  "transcript": transcript.decode(errors="replace")[-4000:]})

        try:
            wait_for_evidence("session_start", before_start, 60)
            # Use the pre-Popen baseline: the initial agent_end can be recorded
            # before session_start becomes visible in the evidence file.
            wait_for_evidence("agent_end", before_start, 60)
            before_command = len(read_rows(evidence))
            os.write(master, f"{text}\r".encode())
            after_command = wait_for_evidence("agent_end", before_command, 60)
            delivered = [row for row in after_command[before_command:]
                         if row.get("pid") == proc.pid and row.get("kind") == "procedure"]
            assert len(delivered) == 1, (text, delivered)
            # The assertion is about the completed command turn and recorded
            # procedure; quit through Pi so successful runs also prove clean
            # native teardown rather than relying on a signal.
            os.write(master, b"\x1b[200~/quit\x1b[201~\r")
            quit_deadline = time.monotonic() + 10
            while proc.poll() is None and time.monotonic() < quit_deadline:
                drain()
                time.sleep(0.05)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            if proc.returncode != 0:
                raise AssertionError({"command": text, "pid": proc.pid, "stage": "quit",
                                      "exitCode": proc.returncode,
                                      "evidence": read_rows(evidence)[before_command:],
                                      "transcript": transcript.decode(errors="replace")[-4000:]})
            details = delivered[0]["details"]
            assert isinstance(details, dict), details
            result = {"command": text, "exitCode": proc.returncode, "details": details}
            run_results.append(result)
            return details
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            os.close(master)

    for capability in user_capabilities:
        details = run_one(f"/matt-pocock {capability} user command")
        assert details.get("capability") == capability and details.get("request") == "user command", details
    for route in routes:
        details = run_one(f"/matt-pocock {route} user workflow")
        assert details.get("route") == route and details.get("request") == "user workflow", details
    rows = read_rows(evidence)
    procedures = [row for row in rows if row["kind"] == "procedure"]
    print(json.dumps({"userCommands": len(procedures), "runs": run_results}))


def run_rpc_boundaries(pi: str, root: Path) -> None:
    """Exercise native AgentSession tree and compaction events over RPC."""
    evidence = root / "rpc.jsonl"
    session = root / "rpc-session.jsonl"
    env = isolated_env(root, evidence, [call("matt_pocock_workflow", mode="workflow", route=next(iter(catalog_inventory()[0])))])
    env["PI_RUNTIME_COMPACTION_STUB"] = "1"
    proc = subprocess.Popen([*command(pi, mode="rpc", session=session)], cwd=root, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin and proc.stdout
    rpc_buffer = bytearray()

    def send(value: dict[str, object]) -> None:
        proc.stdin.write((json.dumps(value) + "\n").encode())
        proc.stdin.flush()

    def wait_for(predicate: Callable[[dict[str, object]], bool], timeout: float = 30) -> list[dict[str, object]]:
        nonlocal rpc_buffer
        rows: list[dict[str, object]] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # A single os.read may contain several RPC frames. Consume all
            # buffered frames before waiting for another fd readiness signal;
            # select() cannot see bytes already held in this userspace buffer.
            while b"\n" in rpc_buffer:
                line, _, remainder = rpc_buffer.partition(b"\n")
                rpc_buffer = bytearray(remainder)
                row = json.loads(line)
                rows.append(row)
                if predicate(row):
                    return rows
            ready, _, _ = select.select([proc.stdout], [], [], 0.2)
            if not ready:
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            rpc_buffer.extend(chunk)
        error = proc.stderr.read().decode(errors="replace") if proc.poll() else ""
        raise AssertionError(f"RPC event deadline exceeded: {rows}; stderr={error}")

    def wait_evidence(kind: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(row.get("kind") == kind for row in read_rows(evidence)):
                return
            time.sleep(0.05)
        raise AssertionError(f"Native extension event {kind} was not observed: {read_rows(evidence)}")

    try:
        send({"id": "prompt", "type": "prompt", "message": "Start the native RPC workflow"})
        wait_for(lambda row: row.get("type") == "agent_end")
        send({"id": "tree-back", "type": "prompt", "message": "/runtime-tree back"})
        wait_evidence("session_tree")
        wait_for(lambda row: row.get("id") == "tree-back" and row.get("type") == "response")
        send({"id": "tree-active", "type": "prompt", "message": "/runtime-tree active"})
        wait_for(lambda row: row.get("id") == "tree-active" and row.get("type") == "response")
        tree_rows = [row for row in read_rows(evidence) if row["kind"] == "session_tree"]
        assert len(tree_rows) >= 2, read_rows(evidence)
        assert "matt_pocock_active" not in tree_rows[-2]["activeTools"], tree_rows
        assert "matt_pocock_active" in tree_rows[-1]["activeTools"], tree_rows
        send({"id": "compact", "type": "compact", "customInstructions": "Keep the active Matt Pocock workflow state."})
        wait_for(lambda row: row.get("id") == "compact" and row.get("type") == "response", 60)
        wait_evidence("session_compact", 60)
        assert any(row["kind"] == "session_before_compact" for row in read_rows(evidence))
        compacted_entries = [json.loads(line) for line in session.read_text().splitlines()]
        compaction = [entry for entry in compacted_entries if entry.get("type") == "compaction"][-1]
        assert compaction.get("details", {}).get("procedureSourcePreserved") is True, compaction
        assert compaction.get("summary") == "Preserve the complete Matt Pocock procedure source and active workflow state.", compaction
        compact_checkpoint = len(read_rows(evidence))
        send({"id": "after-compact", "type": "prompt", "message": "Continue with the restored Matt Pocock workflow source."})
        wait_for(lambda row: row.get("type") == "agent_end", 60)
        post_compact_rows = read_rows(evidence)[compact_checkpoint:]
        expected_source_ids = procedure_closure([route_entry(next(iter(catalog_inventory()[0])))])
        assert any(row["kind"] == "model_context" and row["procedureSourceComplete"]
                   and expected_source_ids.issubset(set(row["procedureSourceIds"]))
                   for row in post_compact_rows), post_compact_rows
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    rows = read_rows(evidence)
    tree = [row for row in rows if row["kind"] == "session_tree"]
    compact = [row for row in rows if row["kind"] == "session_compact"]
    assert tree and compact, rows
    assert "matt_pocock_active" not in tree[-2]["activeTools"]
    assert "matt_pocock_active" in tree[-1]["activeTools"]
    assert all("matt_pocock_active" in row["activeTools"] for row in compact)
    assert any(row["kind"] == "procedure" and row["display"] is False
               and row["hasProcedureHeading"] and row["contentBytes"] > 100 for row in rows), rows
    assert any(row["kind"] == "model_context" and row["procedureSourceComplete"]
               and row["procedureSourceBytes"] > 100 for row in rows), rows
    print("rpc boundaries: native session_tree switched inactive/active branches and session_compact restored source")


def run_literal_commands(pi: str, root: Path) -> None:
    """Exercise literal slash commands through Pi's native RPC command router."""
    counts = {"literal": 0, "control": 0, "menu": 0}
    case_names: list[str] = []

    class RpcCase:
        def __init__(self, name: str) -> None:
            self.name = name
            self.case_root = root / f"literal-{len(case_names):02d}-{name}"
            self.case_root.mkdir(parents=True, exist_ok=True)
            self.evidence = self.case_root / "evidence.jsonl"
            self.session = self.case_root / "session.jsonl"
            self.env = isolated_env(self.case_root, self.evidence, [])
            self.proc = subprocess.Popen([*command(pi, mode="rpc", session=self.session)],
                                         cwd=self.case_root, env=self.env, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert self.proc.stdin and self.proc.stdout
            self.buffer = bytearray()
            self.events: list[dict[str, object]] = []
            self.prompt_number = 0
            case_names.append(name)

        def send(self, value: dict[str, object]) -> None:
            assert self.proc.stdin
            self.proc.stdin.write((json.dumps(value) + "\n").encode())
            self.proc.stdin.flush()

        def wait_for(self, predicate: Callable[[dict[str, object]], bool], timeout: float = 60) -> dict[str, object]:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                while b"\n" in self.buffer:
                    line, _, remainder = self.buffer.partition(b"\n")
                    self.buffer = bytearray(remainder)
                    if not line:
                        continue
                    row = json.loads(line)
                    self.events.append(row)
                    if predicate(row):
                        return row
                ready, _, _ = select.select([self.proc.stdout], [], [], 0.2)
                if ready:
                    chunk = os.read(self.proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    self.buffer.extend(chunk)
                if self.proc.poll() is not None:
                    break
            stderr = self.proc.stderr.read().decode(errors="replace") if self.proc.poll() else ""
            raise AssertionError({"case": self.name, "stage": "rpc-event", "exitCode": self.proc.poll(),
                                  "events": self.events[-40:], "evidence": read_rows(self.evidence)[-40:],
                                  "stderr": stderr[-4000:]})

        def prompt(self, message: str, *, turn: bool = False, success: bool = True,
                   wait_response: bool = True) -> dict[str, object]:
            evidence_before = len(read_rows(self.evidence))
            event_before = len(self.events)
            self.prompt_number += 1
            identifier = f"prompt-{self.prompt_number}"
            self.send({"id": identifier, "type": "prompt", "message": message})
            if not wait_response:
                return {"id": identifier, "pending": True}
            response = self.wait_for(lambda row: row.get("type") == "response" and row.get("id") == identifier)
            assert response.get("success") is success, {"case": self.name, "message": message, "response": response}
            if turn:
                self.wait_for(lambda row: row.get("type") == "agent_end")
                rows = read_rows(self.evidence)
                assert any(row.get("kind") == "agent_end" for row in rows[evidence_before:]), {
                    "case": self.name, "message": message, "evidence": rows[evidence_before:]
                }
            else:
                rows = read_rows(self.evidence)
                assert not any(row.get("kind") == "agent_end" for row in rows[evidence_before:]), {
                    "case": self.name, "message": message, "evidence": rows[evidence_before:]
                }
            return response

        def select(self, option: str | None = None) -> dict[str, object]:
            request = self.wait_for(lambda row: row.get("type") == "extension_ui_request"
                                    and row.get("method") == "select")
            choices = request.get("options")
            assert isinstance(choices, list) and all(isinstance(choice, str) for choice in choices), request
            if option is None:
                self.send({"type": "extension_ui_response", "id": request["id"], "cancelled": True})
            else:
                match = next((choice for choice in choices if choice == option or choice.startswith(option)), None)
                assert match is not None, {"requested": option, "choices": choices}
                self.send({"type": "extension_ui_response", "id": request["id"], "value": match})
            return request

        def notify(self, *, message: str | None = None, notify_type: str | None = None) -> dict[str, object]:
            row = next((event for event in reversed(self.events)
                        if event.get("type") == "extension_ui_request" and event.get("method") == "notify"), None)
            if row is None:
                row = self.wait_for(lambda event: event.get("type") == "extension_ui_request"
                                    and event.get("method") == "notify")
            if message is not None:
                assert row.get("message") == message, row
            if notify_type is not None:
                assert row.get("notifyType") == notify_type, row
            return row

        def extension_error(self, fragment: str) -> dict[str, object]:
            row = next((event for event in reversed(self.events)
                        if event.get("type") == "extension_error"), None)
            assert row is not None and fragment in str(row.get("error")), {"fragment": fragment, "events": self.events}
            return row

        def rows(self) -> list[dict[str, object]]:
            return read_rows(self.evidence)

        def procedures(self, baseline: int = 0) -> list[dict[str, object]]:
            return [row for row in self.rows()[baseline:] if row.get("kind") == "procedure"]

        def latest_state(self) -> dict[str, object] | None:
            entries = [row for row in self.rows() if row.get("kind") == "append"
                       and isinstance(row.get("data"), dict)]
            return entries[-1]["data"] if entries else None

        def close(self) -> None:
            if self.proc.stdin:
                self.proc.stdin.close()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
            assert self.proc.returncode == 0, {"case": self.name, "exitCode": self.proc.returncode,
                                               "events": self.events[-20:], "evidence": self.rows()[-20:]}

    def finish(case: RpcCase, group: str) -> None:
        case.close()
        counts[group] += 1

    # Inactive controls and freeform/alias routing all use the real command registry.
    case = RpcCase("inactive-controls")
    case.prompt("/matt-pocock status")
    case.notify(message="Matt Pocock workflow: inactive", notify_type="info")
    case.prompt("/matt-pocock transition implement")
    case.notify(message="No active Matt Pocock workflow.", notify_type="warning")
    case.prompt("/matt-pocock complete")
    case.extension_error("No active Matt Pocock workflow.")
    case.prompt("/matt-pocock complete extra")
    case.notify(notify_type="error")
    procedure_before = len(case.rows())
    case.prompt("/matt-pocock unknown freeform request", turn=True)
    routed = case.procedures(procedure_before)
    assert len(routed) == 1 and routed[0]["details"].get("request") == "unknown freeform request", routed
    alias_before = len(case.rows())
    case.prompt("/matt-pocock tight-red-loop alias request", turn=True)
    alias_rows = case.procedures(alias_before)
    assert len(alias_rows) == 1 and alias_rows[0]["details"].get("capability") == "diagnosing-bugs", alias_rows
    freeform_before = len(case.rows())
    case.prompt("/matt-pocock clarify-goal should route normally", turn=True)
    freeform_rows = case.procedures(freeform_before)
    assert len(freeform_rows) == 1 and freeform_rows[0]["details"].get("request") == "clarify-goal should route normally", freeform_rows
    finish(case, "literal")

    # A legal path reaches implement and code-review; invalid and missing arguments
    # are checked while the workflow remains active.
    case = RpcCase("transition-controls")
    case.prompt("/matt-pocock idea-to-ship start", turn=True)
    for target in ("to-spec", "to-tickets", "implement", "code-review"):
        case.prompt(f"/matt-pocock transition    {target}", turn=True)
    case.prompt("/matt-pocock transition badtarget")
    case.extension_error("Cannot transition")
    case.prompt("/matt-pocock transition", wait_response=False)
    case.select(None)
    case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-7")
    case.prompt("/matt-pocock complete extra")
    case.notify(notify_type="error")
    assert case.latest_state() and case.latest_state().get("status") == "active", case.latest_state()
    case.prompt("/matt-pocock status")
    case.notify(notify_type="info")
    case.prompt("/matt-pocock complete")
    case.notify(notify_type="info")
    assert case.latest_state() and case.latest_state().get("status") == "completed", case.latest_state()
    finish(case, "control")

    case = RpcCase("cancel-reason")
    case.prompt("/matt-pocock idea-to-ship cancel case", turn=True)
    case.prompt("/matt-pocock cancel because user changed scope")
    case.notify(notify_type="info")
    state = case.latest_state()
    assert state and state.get("status") == "cancelled" and state.get("reason") == "because user changed scope", state
    finish(case, "control")

    case = RpcCase("end-alias")
    case.prompt("/matt-pocock idea-to-ship end case", turn=True)
    case.prompt("/matt-pocock end finished by user")
    case.notify(notify_type="info")
    state = case.latest_state()
    assert state and state.get("status") == "cancelled" and state.get("reason") == "finished by user", state
    finish(case, "control")

    # An active route is atomically cancelled before an unknown command is routed
    # as freeform context; the new request still completes a native turn.
    case = RpcCase("active-supersession")
    case.prompt("/matt-pocock idea-to-ship active request", turn=True)
    procedure_before = len(case.rows())
    case.prompt("/matt-pocock unknown active request", turn=True)
    procedure_rows = case.procedures(procedure_before)
    assert len(procedure_rows) == 1 and procedure_rows[0]["details"].get("request") == "unknown active request", procedure_rows
    state = case.latest_state()
    assert state and state.get("status") == "cancelled" and "superseded" in str(state.get("reason")).lower(), state
    finish(case, "literal")

    # Menu routing is driven only by extension_ui_request/response. The selected
    # workflow and capability then prove their own native turn evidence.
    case = RpcCase("menu-workflow")
    procedure_before = len(case.rows())
    case.prompt("/matt-pocock", wait_response=False)
    case.select("Start a workflow")
    case.select("Start an idea-to-ship flow")
    case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-1")
    case.wait_for(lambda row: row.get("type") == "agent_end")
    assert len(case.procedures(procedure_before)) == 1, case.rows()
    finish(case, "menu")

    case = RpcCase("menu-capability")
    procedure_before = len(case.rows())
    case.prompt("/matt-pocock", wait_response=False)
    case.select("Run a standalone capability")
    case.select("Grill Me")
    case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-1")
    case.wait_for(lambda row: row.get("type") == "agent_end")
    capability_rows = case.procedures(procedure_before)
    assert len(capability_rows) == 1 and capability_rows[0]["details"].get("capability") == "grill-me", capability_rows
    finish(case, "menu")

    case = RpcCase("menu-cancel-and-context")
    case.prompt("/matt-pocock", wait_response=False)
    case.select(None)
    case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-1")
    case.prompt("/matt-pocock", wait_response=False)
    case.select("View current workflow")
    case.notify(message="Matt Pocock workflow: inactive", notify_type="info")
    case.prompt("/matt-pocock", wait_response=False)
    case.select("Start a task")
    case.wait_for(lambda row: row.get("type") == "response" and row.get("id") == "prompt-3")
    case.wait_for(lambda row: row.get("type") == "agent_end")
    finish(case, "menu")

    print(json.dumps({"literalCommandCases": len(case_names), **counts, "caseNames": case_names}))


def main() -> None:
    pi = shutil.which("pi")
    assert pi, "Pi v1.0 CLI is required"
    with tempfile.TemporaryDirectory(prefix="matt-pocock-runtime-") as directory:
        root = Path(directory)
        run_matrix(pi, root)
        run_restart(pi, root)
        run_rpc_boundaries(pi, root)
        run_reference_coverage(pi, root)
        run_user_commands(pi, root)
        run_literal_commands(pi, root)
        print("MP_RUNTIME_MATRIX_DONE=matrix,restart,rpc,user")


if __name__ == "__main__":
    main()
