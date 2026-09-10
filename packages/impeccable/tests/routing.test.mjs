import assert from 'node:assert/strict';
import { test } from 'node:test';
import { routeFreeform } from '../src/routing.ts';

const entries = [
  { id: 'critique', implemented: true, closestImplemented: 'critique', en: ['review', 'critique', 'heuristic'], zh: ['评审', '点评', '打分'], hint: '' },
  { id: 'audit', implemented: true, closestImplemented: 'audit', en: ['audit', 'a11y', 'all checks', 'scan'], zh: ['审计', '检查', '无障碍', '全面检查', '体检'], hint: '' },
  { id: 'optimize', implemented: false, closestImplemented: 'audit', en: ['slow', 'performance'], zh: ['优化'], hint: '' },
  { id: 'polish', implemented: true, closestImplemented: 'polish', en: ['polish', 'fix', 'final pass'], zh: ['润色', '修复', '满分'], hint: '' },
  { id: 'colorize', implemented: true, closestImplemented: 'colorize', en: ['color', 'vibrant', 'palette'], zh: ['配色'], hint: '' },
  { id: 'layout', implemented: true, closestImplemented: 'layout', en: ['layout', 'spacing', 'alignment'], zh: ['布局', '间距'], hint: '' },
  { id: 'bolder', implemented: false, closestImplemented: 'polish', en: ['bland', 'amplify', 'too safe'], zh: ['平淡'], hint: '' },
  { id: 'shape', implemented: false, closestImplemented: null, en: ['plan ux', 'design brief'], zh: ['规划'], hint: '' },
  { id: 'craft', implemented: false, closestImplemented: null, en: ['craft', 'shape-then-build'], zh: ['构建'], hint: '', aliasOf: 'shape', deprecated: true },
];

const allImplemented = id => ['critique', 'audit', 'polish', 'colorize', 'layout'].includes(id);

test('check-then-fix routes evaluate-first with fix queued', () => {
  const routed = routeFreeform('运行全部检查，然后fix，直到满分', entries, allImplemented);
  assert.equal(routed?.target, 'audit');
  assert.equal(routed?.queued, 'polish');
});

test('chinese audit intent loads audit', () => {
  const routed = routeFreeform('帮我审计一下这个落地页的无障碍', entries, allImplemented);
  assert.equal(routed?.target, 'audit');
  assert.equal(routed?.recognized, 'audit');
});

test('close second match is named runner-up', () => {
  const routed = routeFreeform('make the palette more vibrant with better spacing', entries, allImplemented);
  assert.equal(routed?.target, 'colorize');
  assert.equal(routed?.runnerUp, 'layout');
});

test('recognized but unported intent loads closest and states gap', () => {
  const routed = routeFreeform('this looks too safe and bland, amplify it', entries, allImplemented);
  assert.equal(routed?.target, 'polish');
  assert.equal(routed?.unported, 'bolder');
});

test('deprecated craft aliases shape with a note', () => {
  const routed = routeFreeform('craft a new hero section', entries, allImplemented);
  assert.equal(routed?.recognized, 'shape');
  assert.equal(routed?.target, null);
  assert.match(routed?.aliasNote ?? '', /deprecated alias/);
});

test('unrecognized freeform returns null for legacy guidance', () => {
  assert.equal(routeFreeform('make the pricing hero feel more confident', entries, allImplemented), null);
  assert.equal(routeFreeform('下一步？', entries, allImplemented), null);
});

test('paraphrased check-then-optimize routes to audit', () => {
  const routed = routeFreeform('全面体检一遍然后优化', entries, allImplemented);
  assert.equal(routed?.target, 'audit');
});

test('ascii triggers respect word boundaries', () => {
  assert.equal(routeFreeform('prefix the component library', entries, allImplemented), null);
  assert.equal(routeFreeform('fix the component library', entries, allImplemented)?.target, 'polish');
});
