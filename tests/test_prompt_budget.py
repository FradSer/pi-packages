from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Per-turn system-prompt ceilings, measured with worst-case inputs. Each package
# owns a section; this test is the single place that notices when a section grows
# past the size it earns, which is how the total stays governed rather than
# incidental. Raise a ceiling deliberately with the change that needs it.
CEILINGS = {
    "clMemoryIndex": 6_100,
    "tmIdleLeader": 3_600,
    # Raised for the attempt-bound recovery contract: a Leader must know that
    # failed Work returns as `pending/recovery-required` and waits for an
    # explicit `work assign`, so it does not wait for a claim that never comes.
    "tmActiveLeader": 5_250,
    # Raised for the same change: a Worker must know its turn is bound to one
    # Assignment Attempt and must end the turn after a terminal outcome.
    "tmWorker": 2_150,
    "mpInactiveCatalog": 2_650,
    "utilPeerRecap": 1_550,
    "monitorSection": 800,
    "contextSection": 250,
    "srRoutingSuggestion": 400,
}
# Worst-case leader turn: memory index + active leader guidance + catalog + peer
# recap + monitor + research + one routing suggestion. Measured at ~15.9K, so the
# ceiling is the governance line, not a claim that no section could be smaller.
# Raised by 100 for the attempt-bound recovery contract, which adds mandatory
# instruction bytes to the active Leader and Worker sections.
TOTAL_CEILING = 16_100


def measure() -> dict[str, int]:
    script = """
    import { formatMemoriesBlock, type MemoryLoadResult } from './packages/continual-learning/extensions/memory-files.ts';
    import { buildIdleLeaderGuidance, buildTeamLeaderGuidance, WORKER_GUIDANCE } from './packages/agent-teams/src/guidance.ts';
    import { availableWorkflowsGuidance } from './packages/matt-pocock/src/workflow.ts';
    import { formatCrossSessionRecap } from './packages/utils/extensions/sessions.ts';
    import { routingGuidance } from './packages/skill-router/src/router.ts';
    import registerMonitor from './packages/monitor/src/index.ts';
    import registerContextGuidance from './packages/context/extensions/context-command.ts';

    const memory: MemoryLoadResult = {
      totalEntries: 60, limitedEntries: 0, unavailableEntries: 0, omittedEntries: 0,
      maxTotalChars: 6_000,
      indexes: [
        { source: 'public', readPath: '/repo/.memory/MEMORY.md', rootPath: '/repo/.memory', available: true },
        { source: 'harness', readPath: '/Users/x/.pi/agent/memory/--repo--/MEMORY.md', rootPath: '/Users/x/.pi/agent/memory/--repo--', available: true },
      ],
      entries: Array.from({ length: 60 }, (_, index) => ({
        filename: `project_entry_${String(index).padStart(2, '0')}_with_a_representative_name.md`,
        source: index % 2 === 0 ? 'harness' : 'public',
        readPath: `/Users/x/.pi/agent/memory/--repo--/entry_${index}.md`,
        content: '',
        description: `Relevant when the task touches area ${index} of the project and needs the recorded decision.`,
      })),
    };
    const peers = Array.from({ length: 5 }, (_, index) => ({
      sessionId: `sess-${index}`, sessionName: `Peer ${index}`, pid: 1000 + index, cwd: '/repo',
      startedAt: Date.now() - 60_000, updatedAt: Date.now() - index * 1000,
      status: 'running', latestGoal: 'g'.repeat(400), recap: 'r'.repeat(400),
      modifiedFiles: Array.from({ length: 5 }, (_, file) => `packages/example/src/file_${file}.ts`),
    }));

    // The two sections that only exist inside a hook are measured through it.
    const hooks: Record<string, (event: unknown) => Promise<unknown>> = {};
    const noop = () => {};
    const monitorTools = new Map<string, unknown>();
    registerMonitor({
      on: (name, handler) => { hooks[`monitor:${name}`] = handler; },
      registerTool: (tool) => { monitorTools.set(tool.name, tool); },
      registerCommand: noop, registerMessageRenderer: noop, registerEntryRenderer: noop,
      appendEntry: noop, setActiveTools: noop, getActiveTools: () => [],
    } as never);
    registerContextGuidance({
      on: (name, handler) => { hooks[`context:${name}`] = handler; },
    } as never);
    const section = async (key: string) => {
      const result = await hooks[key]({ systemPrompt: '' }) as { systemPrompt?: string } | undefined;
      return (result?.systemPrompt ?? '').length;
    };

    console.log(JSON.stringify({
      clMemoryIndex: formatMemoriesBlock(memory).length,
      tmIdleLeader: buildIdleLeaderGuidance().length,
      tmActiveLeader: buildTeamLeaderGuidance().length,
      tmWorker: WORKER_GUIDANCE.length,
      mpInactiveCatalog: availableWorkflowsGuidance().length,
      utilPeerRecap: formatCrossSessionRecap(peers as never).length,
      monitorSection: await section('monitor:before_agent_start'),
      contextSection: await section('context:before_agent_start'),
      srRoutingSuggestion: routingGuidance({
        collectionId: 'marketing', skillName: 'schema',
        skillPath: '/Users/x/.pi/agent/skill-router/exposed/collections/marketing/leaves/schema/SKILL.md',
      } as never).length,
    }));
    """
    result = subprocess.run(
        ["bun", "-e", script],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_every_injected_section_stays_within_its_documented_ceiling() -> None:
    measured = measure()
    assert set(measured) == set(CEILINGS), "every governed section is measured"
    for name, ceiling in CEILINGS.items():
        assert measured[name] <= ceiling, f"{name} injected {measured[name]} chars, ceiling {ceiling}"


def test_worst_case_leader_turn_stays_within_the_total_ceiling() -> None:
    measured = measure()
    total = (
        measured["clMemoryIndex"]
        + measured["tmActiveLeader"]
        + measured["mpInactiveCatalog"]
        + measured["utilPeerRecap"]
        + measured["monitorSection"]
        + measured["contextSection"]
        + measured["srRoutingSuggestion"]
    )
    assert total <= TOTAL_CEILING, f"worst-case prompt injection is {total} chars, ceiling {TOTAL_CEILING}"