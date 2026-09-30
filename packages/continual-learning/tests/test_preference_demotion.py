"""A stated preference must not reach the project surface, whatever the planner declared.

The parent already refuses a plan that declares ``preference`` with a ``safe``
classification, so a declared contradiction cannot leak. It could not catch a
*mislabel*: the planner declaring ``project`` and ``safe`` for something the user
stated as a personal preference. The live smoke reproduced that three runs in a
row, because a guard on the declared kind is only as strong as the planner's
honesty about it.

The demotion is one-directional by construction. It can only move ``safe`` to
``private``, so a false positive costs a collaborator one lookup and never costs
the user their privacy.
"""

from __future__ import annotations

from support import isolated_run_bun

SNIPPET = r"""
      import { normalizeNewMemoryProposals, statesPreferenceAsSuch } from './packages/continual-learning/extensions/consolidation-run.ts';
      const entries = [
        { message: { role: 'user', content: 'I prefer concise progress updates.' } },
        { message: { role: 'user', content: 'This project ships through the canary channel first.' } },
      ];
      const proposal = (overrides) => ({
        name: 'project_probe.md', kind: 'project', content: 'A durable statement.',
        evidence: [{ index: 0, source: 'user', quote: entries[0].message.content, count: 1 }],
        ...overrides,
      });
      const normalize = (over) => {
        try {
          // `contextEnabled` is what makes a snapshot eligible to ground
          // proposals; without it the parent refuses before classification.
          const out = normalizeNewMemoryProposals({ newMemories: [proposal(over)] }, { contextEnabled: true, entries });
          return out[0].classification;
        } catch (error) { return `error: ${error.message}`; }
      };
      console.log(JSON.stringify({
        statedPreferenceDetected: [
          statesPreferenceAsSuch('I prefer concise updates.'),
          statesPreferenceAsSuch('我更喜欢简短更新。'),
          statesPreferenceAsSuch('This project ships through the canary channel first.'),
          statesPreferenceAsSuch('Run bun run check to verify.'),
        ],
        // The claim itself is checked, not only the quote it cites. A live run
        // cited an unrelated sentence and a preference was mirrored anyway.
        contentStatesIt: (() => {
          try {
            const out = normalizeNewMemoryProposals({ newMemories: [{
              ...proposal({ classification: 'safe' }),
              content: 'The user prefers concise progress updates.',
              evidence: [{ index: 1, source: 'user', quote: entries[1].message.content, count: 1 }],
            }] }, { contextEnabled: true, entries });
            return out[0].classification;
          } catch (error) { return `error: ${error.message}`; }
        })(),
        mislabelledSafe: normalize({ classification: 'safe' }),
        honestSafe: normalize({
          evidence: [{ index: 1, source: 'user', quote: entries[1].message.content, count: 1 }],
        }),
        explicitPrivate: normalize({ classification: 'private' }),
        declaredContradiction: normalize({ kind: 'preference', classification: 'safe' }),
      }));
"""


def test_a_stated_preference_is_demoted_whatever_the_planner_declared() -> None:
    value = isolated_run_bun(SNIPPET)
    detected = value["statedPreferenceDetected"]
    assert detected[0] is True, value
    assert detected[1] is True, value
    # The pattern must not fire on ordinary project or tooling statements, or
    # every safe entry would be demoted and the shared surface would go empty.
    assert detected[2] is False, value
    assert detected[3] is False, value

    # A planner that says `project` + `safe` about a stated preference is
    # demoted rather than trusted.
    assert value["mislabelledSafe"] == "private", value
    # A proposal that states the preference in its own body is demoted even when
    # it cites evidence that does not mention one.
    assert value["contentStatesIt"] == "private", value
    # A project fact resting on ordinary evidence stays shareable.
    assert value["honestSafe"] == "safe", value
    assert value["explicitPrivate"] == "private", value
    # A declared contradiction resolves like a stated preference: the knowledge
    # is kept and made private. Rejecting threw away real learning over a label
    # error and aborted the phase.
    assert value["declaredContradiction"] == "private", value
