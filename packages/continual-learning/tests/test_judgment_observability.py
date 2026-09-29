"""Judgment observability: the measurement must be readable, and the fact that
it is running must be visible.

The whole increment exists to replace a guessed threshold with a measured one.
That is only possible if the measurement can be read, so a report that exists
but is reachable only from a test is a premise failure, not an omission.
"""

from __future__ import annotations

import json

from support import isolated_run_bun

AGENT_DIAGNOSTIC = "incremental-drift-selector"


def test_the_judgment_verb_is_gone_and_its_arguments_are_rejected(tmp_path) -> None:
    """`/consolidate` already reports a run, so the shadow measurement rides that
    receipt rather than a second command the user has to remember."""
    result = isolated_run_bun(
        r"""
      import fs from 'node:fs';import path from 'node:path';
      import {handleLearningManagement} from './packages/continual-learning/extensions/learning-management.ts';
      const cwd=path.join(process.env.CONTROL_TEST_ROOT,'project');fs.mkdirSync(cwd,{recursive:true});
      const notices=[],handled=[];
      const ctx={cwd,hasUI:false,ui:{notify:(text,type)=>notices.push({text,type})}};
      const dependencies={readSettings:async()=>({autoMemory:true}),writeSettings:async()=>{},busy:()=>false};
      handled.push(await handleLearningManagement('judgment',ctx,dependencies));
      handled.push(await handleLearningManagement('history',ctx,dependencies));
      console.log(JSON.stringify({handled,notices}));
    """,
        env={"CONTROL_TEST_ROOT": str(tmp_path)},
    )
    assert result["handled"] == [False, True], result
    # The removed verb notified nothing, and `history` still works, so the verb
    # list is not simply broken.
    assert len(result["notices"]) == 1, result
    assert "No learning history" in result["notices"][0]["text"], result


def test_a_receipt_carries_the_shadow_measurement(tmp_path) -> None:
    result = isolated_run_bun(
        r"""
      import fs from 'node:fs';import path from 'node:path';
      import { formatLearningSummary, learningSummaryDetails } from './packages/continual-learning/extensions/learning-efficiency.ts';
      const receipt={
        kind:'learning-pipeline-receipt', version:1, mode:'manual',
        screen:{memory:true,harness:false,agents:false,reasons:[]},
        attempts:[{phase:'memory',attempt:0,outcome:'applied',durationMs:10,operations:2}],
        totals:{input:10,output:2,cacheRead:0,cacheWrite:0,totalTokens:12},costAvailable:false,
        operations:2,retries:0,
        judgment:{model:'jev-1.13.0',observations:42,agreementRate:0.78,proposalsJudged:12,reusable:9,oneOff:3,surfaces:['harness-operations']},
      };
      const unmeasured={...receipt, judgment:{...receipt.judgment, agreementRate:null, observations:0}};
      const plain={...receipt}; delete plain.judgment;
      console.log(JSON.stringify({
        measured: formatLearningSummary(receipt),
        unmeasured: formatLearningSummary(unmeasured),
        plain: formatLearningSummary(plain),
        details: learningSummaryDetails(receipt),
      }));
    """,
    )
    assert "shadow judgment jev-1.13.0" in result["measured"], result
    assert "42 observations" in result["measured"], result
    assert "agreement 78%" in result["measured"], result
    # A distribution, not a single verdict: the reader sees the shape.
    assert "proposals 9 reusable / 3 one-off" in result["measured"], result
    assert "surfaces harness-operations" in result["measured"], result
    # Unmeasured is never rendered as zero.
    assert "agreement not yet measured" in result["unmeasured"], result
    assert "0%" not in result["unmeasured"], result
    # Opted-out users see the line they see today.
    assert "shadow" not in result["plain"], result
    assert any("shadow" in line for line in result["details"]), result


def test_an_observation_renders_one_bounded_row(tmp_path) -> None:
    result = isolated_run_bun(
        r"""
      import { initTheme } from '@earendil-works/pi-coding-agent';
      initTheme('dark');
      const renderers = new Map(), entries = [];
      const pi = {
        on: () => {}, registerCommand: () => {}, registerMessageRenderer: () => {},
        sendMessage: () => {}, getCommands: () => [],
        registerEntryRenderer: (type, renderer) => renderers.set(type, renderer),
        appendEntry: (type, data) => entries.push({ type, data }),
      };
      const { registerJudgmentObservability } = await import(
        './packages/continual-learning/extensions/judgment-observability.ts');
      registerJudgmentObservability(pi);
      pi.appendEntry('judgment-observation', { model: 'jev-1.13.0', outcome: 'observed', agrees: true, agreementRate: 1 });
      pi.appendEntry('judgment-observation', { model: 'jev-1.13.0', outcome: 'failed', agrees: false, agreementRate: null, reason: 'Judgment endpoint is unreachable' });
      const render = renderers.get('judgment-observation');
      const theme = { fg: (_c, text) => text, bg: (_c, text) => text, bold: text => text };
      const linesOf = (data, expanded) => render({ data }, { expanded }, theme).render(100)
        .join('\n').split('\n').map((line) => line.trim()).filter(Boolean);
      const rows = entries.map((entry) => linesOf(entry.data, false));
      const expanded = linesOf(entries[0].data, true);
      let malformedSafe = true;
      try {
        linesOf(undefined, false);
        linesOf({ model: 7, outcome: 'nonsense', agrees: 'maybe' }, false);
      } catch { malformedSafe = false; }
      console.log(JSON.stringify({ registered: renderers.has('judgment-observation'), rows, expanded, malformedSafe }));
    """,
    )
    assert result["registered"] is True, result
    assert result["malformedSafe"] is True, result
    assert len(result["rows"]) == 2, result
    first = result["rows"][0]
    # Exactly one content line, whatever the width. A per-verdict dump would put
    # the whole decision surface into the transcript of every settled task.
    assert len(first) == 1, result
    assert "jev-1.13.0" in first[0], result
    assert "agrees" in first[0].lower(), result
    assert "agreement" in result["expanded"][-1].lower(), result
    second = result["rows"][1][0]
    assert "unreachable" in second, result
    # An unmeasured rate is not shown collapsed, and never rendered as 0%.
    assert "0%" not in second, result


def test_an_inactive_judgment_records_no_row(tmp_path) -> None:
    result = isolated_run_bun(
        r"""
      import { initTheme } from '@earendil-works/pi-coding-agent';
      initTheme('dark');
      const entries = [];
      const pi = {
        on: () => {}, registerCommand: () => {}, registerMessageRenderer: () => {},
        sendMessage: () => {}, getCommands: () => [],
        registerEntryRenderer: () => {}, appendEntry: (type, data) => entries.push({ type, data }),
      };
      const { registerJudgmentObservability } = await import(
        './packages/continual-learning/extensions/judgment-observability.ts');
      registerJudgmentObservability(pi);
      const { observeJudgmentShadow } = await import(
        './packages/continual-learning/extensions/judgment-shadow.ts');
      const outcome = await observeJudgmentShadow({
        cwd: process.env.OBSERVABILITY_ROOT,
        contextDigest: 'c'.repeat(64),
        projection: { requestText: 'Fix the build.', harnessEvents: [], touchedPaths: [], skills: [], memories: [] },
        selector: { selected: [], memory: false, harness: false, agents: false },
        config: { env: {}, agentDir: process.env.OBSERVABILITY_ROOT },
      });
      console.log(JSON.stringify({ entries: entries.length, observed: outcome.outcome }));
    """,
        env={"OBSERVABILITY_ROOT": str(tmp_path)},
    )
    assert result["entries"] == 0, result
    assert result["observed"] == "failed", result
