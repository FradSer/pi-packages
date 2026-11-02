from __future__ import annotations

from support import run_bun


def test_preflight_matches_only_the_exact_catalog_row_and_memoizes():
    result = run_bun(r'''
      import { catalogListsModel, createWorkerModelPreflight } from './packages/continual-learning/extensions/worker-model-preflight.ts';
      const table = [
        'provider       model                          context  max-out  thinking  images',
        'cliproxyapi    bailian/deepseek-v4-flash      1M       384K     yes       no',
        'cliproxyapi    gpt-6.1-sol                    256K     64K      yes       yes',
      ].join('\n');
      const calls = [];
      const preflight = createWorkerModelPreflight({
        timeoutMs: 2500,
        listModels: async (command, args, timeout) => { calls.push({ command, args: [...args], timeout }); return { stdout: table }; },
      });
      const exact = await preflight.check('cliproxyapi/bailian/deepseek-v4-flash');
      const repeated = await preflight.check('cliproxyapi/bailian/deepseek-v4-flash');
      const extensionOnly = await preflight.check('cli-proxy/bailian/qwen3.8-flash');
      const prefixOnly = await preflight.check('cliproxyapi/bailian/deepseek');
      const noSeparator = await preflight.check('gpt-6.1-sol');
      console.log(JSON.stringify({ exact, repeated, extensionOnly, prefixOnly, noSeparator,
        parser: { row: catalogListsModel(table, 'cliproxyapi/gpt-6.1-sol'), otherProvider: catalogListsModel(table, 'magpie/gpt-6.1-sol') },
        calls }));
    ''')
    assert result["exact"] is True
    assert result["repeated"] is True
    assert result["extensionOnly"] is False
    assert result["prefixOnly"] is False
    assert result["noSeparator"] is False
    assert result["parser"] == {"row": True, "otherProvider": False}
    # One list call per distinct model; repeats reuse the memoized answer.
    assert len(result["calls"]) == 4, result["calls"]
    for call in result["calls"]:
        # The child's own view: no extensions, then the catalog listing.
        assert call["args"][-2:] == ["-ne", "--list-models"], call
        assert call["timeout"] == 2500, call


def test_preflight_unknown_result_does_not_block_and_is_memoized():
    result = run_bun(r'''
      import { createWorkerModelPreflight } from './packages/continual-learning/extensions/worker-model-preflight.ts';
      let calls = 0;
      const preflight = createWorkerModelPreflight({ listModels: async () => { calls += 1; throw new Error('cli unavailable'); } });
      const first = await preflight.check('session/active');
      const second = await preflight.check('session/active');
      console.log(JSON.stringify({ first: first ?? null, second: second ?? null, calls }));
    ''')
    # An unavailable preflight reports "unknown", never a false block.
    assert result == {"first": None, "second": None, "calls": 1}
