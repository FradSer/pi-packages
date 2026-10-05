"""Render real gateway results: phase titles belong in rows, ids in state."""

from __future__ import annotations

import pytest

from matt_pocock_helpers import PACKAGE, RUNTIME_HARNESS, run_typescript

PHASE_TITLES = {
    "shaping": "Shaping & Requirements",
    "research": "Research & Feasibility",
    "prototype": "Prototyping",
    "to-spec": "Specification Design",
    "to-tickets": "Task Decomposition",
    "implement": "Implementation",
    "code-review": "Code Review",
    "handoff": "Handoff & Summary",
    "mapping": "Initiative Mapping",
    "triage": "Task Triage",
    "feedback-loop": "Reproducing & Diagnostics",
    "survey": "Architecture Survey",
    "design-review": "Architecture Design",
}
ROUTES = ("idea-to-ship", "wayfinding", "triage", "hard-bug", "architecture")


@pytest.fixture(scope="module")
def lifecycle_results() -> dict[str, object]:
    return run_typescript(RUNTIME_HARNESS + """
        import { workflowRoutes, workflowDefinitions, workflowPlacement } from "./packages/matt-pocock/src/catalog.ts";
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime(["bash", "matt_pocock_workflow"]);
        const { tools, events, renderers, entries, ctx } = r;
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: (text) => text };
        const gateway = tools.get("matt_pocock_workflow"), active = tools.get("matt_pocock_active");
        const execute = (tool, args) => tool.execute("test", args, undefined, undefined, ctx);
        const render = (tool, result, expanded = false, width = 160) => tool.renderResult(
          result, { expanded, isPartial: false }, theme, { isError: false, args: {} },
        ).render(width);
        const restore = (state) => events.get("session_start")({}, {
          ...ctx, sessionManager: { getBranch: () => [{ type: "custom", customType: "matt-pocock-workflow", data: state }] },
        });
        const starts = [], phases = [], transitions = [], terminals = [];
        for (const { route, title: routeTitle } of workflowRoutes()) {
          const started = await execute(gateway, { mode: "workflow", route });
          starts.push({ route, routeTitle, details: started.details, rows: render(gateway, started), expanded: render(gateway, started, true) });
          await execute(active, { action: "cancel", reason: "test reset" });
          for (const definition of workflowDefinitions(route)) {
            const placement = workflowPlacement(route, definition.id);
            const state = {
              version: 1, workItemId: `test-${route}-${definition.id}`, route,
              procedure: definition.id, phase: placement.phase, status: "active", loadedReferences: [],
            };
            await restore(state);
            const restored = r.deliveries().at(-1);
            phases.push({
              route, routeTitle, state, restored,
              rows: renderers.get("matt-pocock-procedure")(restored.message, { expanded: false }, theme).render(160),
              expanded: renderers.get("matt-pocock-procedure")(restored.message, { expanded: true }, theme).render(160),
            });
            for (const target of placement.allowedNext) {
              await restore(state);
              const result = await execute(active, { action: "transition", target });
              transitions.push({ route, routeTitle, details: result.details, rows: render(active, result), expanded: render(active, result, true) });
            }
            for (const action of ["complete", "cancel"]) {
              await restore(state);
              const result = await execute(active, action === "cancel" ? { action, reason: "test cancellation" } : { action });
              const status = action === "complete" ? "completed" : "cancelled";
              // Old persisted subjects must not override the event's recorded phase on reload.
              const historical = { ...result, details: { ...result.details, subject: `${route} ${status}` } };
              const narrow = render(active, result, false, 48);
              terminals.push({
                route, routeTitle, action, before: state, details: result.details,
                record: entries.at(-1).data, content: result.content, activeTools: [...r.active()],
                rows: render(active, result), expanded: render(active, result, true), historicalRows: render(active, historical),
                narrowBounded: narrow.every((line) => !line.includes("\\n") && visibleWidth(line) <= 48),
                result, historical,
              });
            }
          }
        }
        await execute(gateway, { mode: "workflow", route: "architecture" });
        const cancelled = terminals.find((item) => item.action === "cancel").historical;
        const cancellationsWithoutReason = [undefined, "", " \\t\\r\\n ", "\\u001b[31m\\u001b[0m", "\\u001b]52;c;QUJD\\u0007"].map((reason) => {
          const historical = { ...cancelled, details: { ...cancelled.details, state: { ...cancelled.details.state, reason } } };
          return { reason: reason ?? null, rows: render(active, historical), expanded: render(active, historical, true) };
        });
        // Rerender after another work item starts: never consult mutable active state.
        for (const item of terminals) {
          const snapshot = JSON.stringify(item.result);
          item.rerenderedRows = render(active, item.result);
          item.rerenderedExpanded = render(active, item.result, true);
          item.historicalRows = render(active, item.historical);
          item.historicalExpanded = render(active, item.historical, true);
          item.unchangedAfterRender = snapshot === JSON.stringify(item.result);
          delete item.result; delete item.historical;
        }
        const historicalTransitions = transitions.map((item) => {
          const historical = { content: [], details: { ...item.details, subject: `${item.route} · old phase title` } };
          return { ...item, rows: render(active, historical), expanded: render(active, historical, true) };
        });
        const loaded = await execute(active, { action: "load", reference: "HTML-REPORT" });
        const standalone = await execute(gateway, { mode: "capability", capability: "research" });
        const reference = await execute(gateway, { mode: "reference", capability: "writing-for-agents", reference: "SKILL-MECHANICS" });
        console.log(JSON.stringify({
          starts, phases, transitions, terminals, historicalTransitions, cancellationsWithoutReason,
          nonWorkflow: Object.fromEntries([
            ["loaded", active, loaded], ["standalone", gateway, standalone], ["reference", gateway, reference],
            ["fallback", active, { content: [{ type: "text", text: "Model-only guidance" }], details: { model: "model-only metadata" } }],
          ].map(([name, tool, result]) => [name, {
            rows: render(tool, result), expanded: render(tool, result, true), details: result.details,
          }])),
        }));
    """)


def assert_phase_row(rows: list[str], label: str, phase: str, route: str, route_title: str, suffix: str = "") -> None:
    header = next(row for row in rows if "[matt pocock]" in row)
    assert f"[matt pocock] {label} · {PHASE_TITLES[phase]}{suffix}" in header
    assert route not in header
    assert f"[matt pocock] {label} · {route_title} · {PHASE_TITLES[phase]}" not in header


def assert_phase_block(rows: list[str], phase: str, route: str) -> None:
    """Messages render the head, a blank band row, then the body."""
    content = [row.strip() for row in rows[1:-1]]
    assert content == ["[matt pocock] started", "", PHASE_TITLES[phase]]
    assert route not in "\n".join(rows)


@pytest.mark.parametrize("route", ROUTES)
def test_workflow_start_rows_use_only_entry_phase(lifecycle_results: dict[str, object], route: str) -> None:
    start = next(item for item in lifecycle_results["starts"] if item["route"] == route)
    assert_phase_row(start["rows"], "started", start["details"]["phase"], route, start["routeTitle"])
    expanded = "\n".join(start["expanded"])
    has_distinct_route = start["routeTitle"] != PHASE_TITLES[start["details"]["phase"]]
    assert (f"route · {start['routeTitle']}" in expanded) is has_distinct_route
    assert f"route · {route}" not in expanded
    assert "phase ·" not in expanded
    assert "procedure-source" not in expanded
    assert ("to expand" in "\n".join(start["rows"])) is has_distinct_route
    assert start["details"]["route"] == route


@pytest.mark.parametrize("route", ROUTES)
def test_restored_procedure_rows_use_recorded_phase(lifecycle_results: dict[str, object], route: str) -> None:
    phases = [item for item in lifecycle_results["phases"] if item["route"] == route]
    assert phases
    for item in phases:
        assert_phase_block(item["rows"], item["state"]["phase"], route)
        # A restore re-delivers the whole active closure, so its message details are
        # the recorded state plus the delivery set this restore showed.
        details = item["restored"]["message"]["details"]
        assert {key: value for key, value in details.items() if key != "deliveredProcedures"} == item["state"]
        assert item["state"]["procedure"] in details["deliveredProcedures"]
        assert item["restored"]["message"]["display"] is False
        assert item["restored"]["options"] == {"triggerTurn": False}
        assert "to expand" not in "\n".join(item["rows"])
        assert item["expanded"] == item["rows"]


@pytest.mark.parametrize("route", ROUTES)
def test_transition_rows_use_destination_phase(lifecycle_results: dict[str, object], route: str) -> None:
    for key in ("transitions", "historicalTransitions"):
        transitions = [item for item in lifecycle_results[key] if item["route"] == route]
        assert transitions
        for item in transitions:
            phase = item["details"]["state"]["phase"]
            assert_phase_row(item["rows"], "event", phase, route, item["routeTitle"])
            assert item["details"]["subject"] == PHASE_TITLES[phase]
            assert item["details"]["action"] == "transition"
            assert "to expand" not in "\n".join(item["rows"])
            assert "action ·" not in "\n".join(item["expanded"])
            assert item["expanded"] == item["rows"]


@pytest.mark.parametrize("action,status", [("complete", "completed"), ("cancel", "cancelled")])
@pytest.mark.parametrize("route", ROUTES)
def test_terminal_rows_use_actual_phase_and_keep_workflow_contract(
    lifecycle_results: dict[str, object], route: str, action: str, status: str,
) -> None:
    terminals = [item for item in lifecycle_results["terminals"] if item["route"] == route and item["action"] == action]
    assert terminals
    for item in terminals:
        before = item["before"]
        phase = before["phase"]
        assert item["details"]["subject"] == f"{PHASE_TITLES[phase]} {status}"
        for key in ("rows", "historicalRows", "rerenderedRows"):
            assert_phase_row(item[key], "event", phase, route, item["routeTitle"], f" {status}")
        terminal = item["details"]["state"]
        assert terminal == item["record"]
        assert terminal["status"] == status
        for key in ("version", "route", "phase", "procedure", "workItemId"):
            assert terminal[key] == before[key]
        if action == "cancel":
            assert terminal["reason"] == "test cancellation"
        assert item["activeTools"] == ["bash", "matt_pocock_workflow"]
        assert f"Workflow {before['workItemId']} {status}." in item["content"][0]["text"]
        assert item["narrowBounded"]
        assert item["details"]["action"] == action
        assert item["unchangedAfterRender"]
        for key in ("expanded", "historicalExpanded", "rerenderedExpanded"):
            expanded = "\n".join(item[key])
            assert "action ·" not in expanded
            assert_phase_row(item[key], "event", phase, route, item["routeTitle"], f" {status}")
            if action == "cancel":
                assert expanded.count("reason · test cancellation") == 1
                assert expanded.count("test cancellation") == 1
            else:
                assert item[key] == item["rows"]
        for key in ("rows", "historicalRows", "rerenderedRows"):
            collapsed = "\n".join(item[key])
            assert ("to expand" in collapsed) is (action == "cancel")
            assert "test cancellation" not in collapsed


def test_cancellation_without_nonblank_reason_does_not_expand(lifecycle_results: dict[str, object]) -> None:
    cases = lifecycle_results["cancellationsWithoutReason"]
    assert [item["reason"] for item in cases] == [None, "", " \t\r\n ", "\x1b[31m\x1b[0m", "\x1b]52;c;QUJD\x07"]
    for item in cases:
        collapsed = "\n".join(item["rows"])
        assert "Shaping & Requirements cancelled" in collapsed
        assert "to expand" not in collapsed
        assert "action ·" not in "\n".join(item["expanded"])
        assert "reason ·" not in "\n".join(item["expanded"])
        assert item["expanded"] == item["rows"]


def test_non_workflow_rows_keep_their_subjects(lifecycle_results: dict[str, object]) -> None:
    expected = {
        "loaded": "event · loaded HTML Report",
        "standalone": "started · Research",
        "reference": "started · Writing For Agents · Skill Mechanics",
        "fallback": "event · workflow updated",
    }
    for key, subject in expected.items():
        result = lifecycle_results["nonWorkflow"][key]
        collapsed = "\n".join(result["rows"])
        assert f"[matt pocock] {subject}" in collapsed
        assert "to expand" not in collapsed
        assert result["expanded"] == result["rows"]
        for hidden in ("action ·", "capability ·", "reference ·", "procedure-source", "Model-only guidance", "model-only metadata"):
            assert hidden not in "\n".join(result["expanded"])
    assert lifecycle_results["nonWorkflow"]["loaded"]["details"]["action"] == "load"
    assert lifecycle_results["nonWorkflow"]["standalone"]["details"] == {"mode": "capability", "capability": "research"}
    assert lifecycle_results["nonWorkflow"]["reference"]["details"] == {
        "mode": "reference", "capability": "writing-for-agents", "reference": "SKILL-MECHANICS",
    }


def test_all_standalone_tool_and_message_names_use_catalog_labels() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import {standaloneCapabilities} from "./packages/matt-pocock/src/catalog.ts";
        const r=runtime();
        const theme={fg:(_c,t)=>t,bg:(_c,t)=>t,bold:t=>t};
        const tool=r.tools.get('matt_pocock_workflow');
        console.log(JSON.stringify(standaloneCapabilities().map(c=>{
          const details={mode:'capability',capability:c.id};
          const rows=tool.renderResult({content:[],details},{expanded:false,isPartial:false},theme,{isError:false,args:{}}).render(160);
          const message=r.renderers.get('matt-pocock-procedure')({content:'model only',details},{expanded:false},theme).render(160);
          const task=r.renderers.get('matt-pocock-procedure')({content:'model only',details:{...details,request:'Keep my exact_task-name'}},{expanded:false},theme).render(160);
          return {id:c.id,label:c.label,rows,message,task};
        })));
    ''')
    assert len(result) == 21
    for entry in result:
        assert f"started · {entry['label']}" in '\n'.join(entry['rows'])
        assert entry['label'] in '\n'.join(entry['message'])
        assert 'Keep my exact_task-name' in '\n'.join(entry['task'])


def test_transition_menu_uses_labels_and_keeps_internal_targets() -> None:
    result=run_typescript(RUNTIME_HARNESS + '''
        const r=runtime(); await r.start(); let menu;
        r.ctx.ui.select=async(title,choices)=>{menu={title,choices};return choices[0];};
        await r.commands.get('matt-pocock').handler('transition',r.ctx);
        console.log(JSON.stringify({menu,state:r.entries.at(-1).data}));
    ''')
    assert 'Hard Bug Diagnosis' in result['menu']['title']
    assert 'Reproducing & Diagnostics' in result['menu']['title']
    assert result['menu']['choices'] == ['Implementation', 'Code Review']
    assert result['state']['procedure'] == 'implement'


def test_all_transition_menu_choices_match_destination_lifecycle_titles() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import { workflowRoutes, workflowDefinitions, workflowPlacement } from "./packages/matt-pocock/src/catalog.ts";
        import { readablePhaseTitle } from "./packages/matt-pocock/src/workflow.ts";
        const menus = [];
        for (const { route } of workflowRoutes()) {
          for (const { id } of workflowDefinitions(route)) {
            const placement = workflowPlacement(route, id);
            if (!placement.allowedNext.length) continue;
            const r = runtime();
            r.setBranch([{type: "custom", customType: "matt-pocock-workflow", data: {
              version: 1, workItemId: "menu-test", route, procedure: id,
              phase: placement.phase, status: "active", loadedReferences: [],
            }}]);
            await r.events.get("session_start")({}, r.ctx);
            let choices;
            r.ctx.ui.select = async (_title, offered) => { choices = offered; return undefined; };
            await r.commands.get("matt-pocock").handler("transition", r.ctx);
            menus.push({choices, expected: placement.allowedNext.map(target => readablePhaseTitle(workflowPlacement(route, target).phase))});
          }
        }
        console.log(JSON.stringify(menus));
    ''')
    assert result
    for menu in result:
        assert menu['choices'] == menu['expected']


def test_all_reference_rows_preserve_names_and_width_including_saved_results() -> None:
    result = run_typescript(RUNTIME_HARNESS + '''
        import { procedureCatalog } from "./packages/matt-pocock/src/catalog.ts";
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime();
        const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text };
        const references = procedureCatalog.filter(item => item.kind === "reference" || item.kind === "asset");
        const cases = references.flatMap(item => [
          ["matt_pocock_active", {action: "load", reference: item.id}],
          ["matt_pocock_active", {action: "load", subject: `loaded ${item.id}`}],
          ["matt_pocock_workflow", {mode: "reference", capability: "writing-for-agents", reference: item.id}],
        ].map(([name, details]) => {
          const render = (width, expanded) => r.tools.get(name).renderResult(
            {content: [{type: "text", text: "Model-only resource body"}], details},
            {expanded, isPartial: false}, theme, {isError: false, args: {}},
          ).render(width);
          return {label: item.label, rows: render(160, false), expanded: render(160, true),
            bounded: [24, 48, 80].every(width => [false, true].every(expanded => render(width, expanded).every(line => !line.includes("\\n") && visibleWidth(line) <= width)))};
        }));
        console.log(JSON.stringify(cases));
    ''')
    assert result
    for case in result:
        assert case['label'] in '\n'.join(case['rows'])
        assert case['bounded']
        assert 'Model-only resource body' not in '\n'.join(case['expanded'])


def test_all_tool_errors_use_shared_failure_style_and_pending_background() -> None:
    result = run_typescript(RUNTIME_HARNESS + r'''
        import { visibleWidth } from "@earendil-works/pi-tui";
        const r = runtime();
        const cases = [...r.tools.values()].map(tool => {
          const backgrounds = [];
          const theme = {fg: (_color, text) => text, bg: (color, text) => {backgrounds.push(color); return text;}, bold: text => text};
          const render = (width, expanded, isError, isPartial) => tool.renderResult(
            {content: [{type: "text", text: "Error: invalid target\nTry an allowed target."}], details: {}},
            {expanded, isPartial}, theme, {isError, args: {}},
          ).render(width);
          const failure = render(160, false, true, false);
          render(80, false, false, true);
          return {name: tool.name, failure, errorBackground: backgrounds.includes("toolErrorBg"), pendingBackground: backgrounds.includes("toolPendingBg"),
            bounded: [24, 48, 80].every(width => [false, true].every(expanded => render(width, expanded, true, false).every(line => !line.includes("\n") && visibleWidth(line) <= width)))};
        });
        console.log(JSON.stringify(cases));
    ''')
    assert len(result) == 3
    for case in result:
        assert '[matt pocock] failed ·' in '\n'.join(case['failure'])
        assert case['errorBackground'] and case['pendingBackground'] and case['bounded']
