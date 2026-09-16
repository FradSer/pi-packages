import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { createResolver, MAX_BUNDLE_BYTES } from '../src/resolver.ts';
import { registerImpeccable } from '../src/index.ts';
import { validateCatalog } from '../src/catalog.ts';
import { visibleWidth } from '@earendil-works/pi-tui';

async function fixture(run) {
  const root = mkdtempSync(join(tmpdir(), 'impeccable space '));
  const entries = [
    { id: 'polish', kind: 'capability', invocation: 'model', file: 'procedures/polish.md', label: 'Polish', requires: ['principles', 'components'], discloses: [{ id: 'motion', when: 'Motion applies' }] },
    { id: 'principles', kind: 'reference', invocation: 'internal', file: 'references/taste/principles.md', label: 'Principles' },
    { id: 'components', kind: 'reference', invocation: 'internal', file: 'references/taste/components.md', label: 'Components', requires: ['principles'] },
    { id: 'motion', kind: 'reference', invocation: 'internal', file: 'references/taste/motion.md', label: 'Motion' },
    { id: 'private', kind: 'reference', invocation: 'internal', file: 'references/taste/private.md', label: 'Private' },
    { id: 'promote', kind: 'capability', invocation: 'user', file: 'procedures/promote.md', label: 'Promote', discloses: [{ id: 'private', when: 'User selected' }] },
  ];
  for (const entry of entries) {
    mkdirSync(join(root, entry.file, '..'), { recursive: true });
    writeFileSync(join(root, entry.file), `# ${entry.id}\n{{PKG_DIR}}/scripts/context.mjs\n`);
  }
  writeFileSync(join(root, 'procedures/polish.md'), '# polish\n[Components](../references/taste/components.md#press)');
  try { return await run(createResolver(root, entries), root, entries); } finally { rmSync(root, { recursive: true, force: true }); }
}

function host(resolver, hasUI = false, choice) {
  const sent = [], messages = [], commands = new Map(), tools = [], renderers = new Map();
  const pi = { registerCommand: (id, command) => commands.set(id, command), registerTool: tool => tools.push(tool), sendUserMessage: (...args) => sent.push(args), sendMessage: (...args) => messages.push(args), registerMessageRenderer: (id, fn) => renderers.set(id, fn) };
  let selects = 0;
  const ctx = { hasUI, ui: { select: async () => { selects++; return choice; }, notify() {} } };
  registerImpeccable(pi, resolver);
  return { sent, messages, renderers, command: commands.get('impeccable'), tool: tools[0], ctx, selects: () => selects };
}

test('required closure once, canonical links, optional per-load paths', () => fixture((resolver, root) => {
  const bundle = resolver.load('polish', 'model');
  assert.deepEqual(bundle.loaded, ['polish', 'principles', 'components']);
  assert.equal(bundle.content.split('# principles').length, 2);
  assert.match(bundle.content, /impeccable:components#press/);
  assert.deepEqual(bundle.availableReferences, [{ id: 'motion', when: 'Motion applies' }]);
  const reference = resolver.load('polish', 'model', 'motion');
  assert.deepEqual(reference.loaded, ['motion']);
  assert.ok(reference.content.includes(root));
  assert.ok(!reference.content.includes('{{PKG_DIR}}'));
  assert.throws(() => resolver.load('polish', 'model', 'private'), /not reachable.*motion/);
  assert.throws(() => resolver.load('promote', 'model'), /explicit user.*\/impeccable promote/);
  assert.throws(() => resolver.load('promote', 'model', 'private'), /explicit user/);
}));

test('oversized UTF-8 bundles fail hard and cancellation propagates', () => fixture((resolver, root) => {
  writeFileSync(join(root, 'references/taste/motion.md'), '界'.repeat(MAX_BUNDLE_BYTES));
  assert.throws(() => resolver.load('polish', 'model', 'motion'), /65536/);
  const controller = new AbortController(); controller.abort();
  assert.throws(() => resolver.load('polish', 'model', undefined, controller.signal), /abort/i);
}));

test('command and tool share bundle; tool never sends a follow-up', async () => {
  await fixture(async (resolver) => {
    const h = host(resolver);
    await h.command.handler('polish src/a b.ts  keep spacing', h.ctx);
    {
      const result = await h.tool.execute('call', { capability: 'polish' }, undefined, undefined, h.ctx);
      assert.ok(h.messages[0][0].content.includes(result.content[0].text));
      assert.ok(h.messages[0][0].content.endsWith('src/a b.ts  keep spacing'));
      assert.deepEqual(h.messages[0][1], { deliverAs: 'followUp', triggerTurn: true });
      assert.equal(h.messages[0][0].customType, 'impeccable-procedure');
      assert.equal(h.messages[0][0].display, true);
      await h.tool.execute('ref', { capability: 'polish', reference: 'motion' }, undefined, undefined, h.ctx);
      assert.equal(h.messages.length, 1);
    }
  });
});

test('headless usage and freeform requests route without a turn; menu cancellation is inert', async () => fixture(async resolver => {
  const h = host(resolver);
  await h.command.handler('', h.ctx);
  assert.equal(h.selects(), 0);
  assert.match(h.messages[0][0].content, /Usage: \/impeccable/);
  assert.equal(h.messages[0][1].triggerTurn, false);
  await h.command.handler('make the pricing hero feel more confident', h.ctx);
  assert.match(h.sent[0][0], /impeccable_load/);
  assert.match(h.sent[0][0], /- \/impeccable polish/);
  assert.match(h.sent[0][0], /max 2 capabilities/);
  assert.ok(h.sent[0][0].endsWith('make the pricing hero feel more confident'));
  assert.deepEqual(h.sent[0][1], { deliverAs: "followUp" });
  assert.equal(h.messages.length, 1);
  const menu = host(resolver, true);
  await menu.command.handler('', menu.ctx);
  assert.equal(menu.selects(), 1);
  assert.equal(menu.sent.length, 0);
}));


test('successful menu selection sends exactly the selected guidance', () => fixture(async resolver => {
  const menu = host(resolver, true, 'polish');
  await menu.command.handler('', menu.ctx);
  assert.equal(menu.selects(), 1);
  assert.equal(menu.sent.length, 0);
  assert.equal(menu.messages.length, 1);
  assert.ok(menu.messages[0][0].content.startsWith('Plan (in order):\n1. /impeccable polish — '));
  assert.ok(menu.messages[0][0].content.endsWith(resolver.load('polish', 'user').content + '\n\nUser target/request:\n'));
  assert.deepEqual(menu.messages[0][1], { deliverAs: 'followUp', triggerTurn: true });
}));

test('explicit user command loads user-only capability but model stays gated', () => fixture(async resolver => {
  const h = host(resolver);
  await h.command.handler('promote chosen preview', h.ctx);
  assert.equal(h.messages.length, 1);
  assert.ok(h.messages[0][0].content.startsWith('Plan for "chosen preview" (in order):\n1. /impeccable promote — '));
  assert.ok(h.messages[0][0].content.endsWith(resolver.load('promote', 'user').content + '\n\nUser target/request:\nchosen preview'));
  await assert.rejects(h.tool.execute('gate', { capability: 'promote' }), /explicit user/);
  await assert.rejects(h.tool.execute('gate-ref', { capability: 'promote', reference: 'private' }), /explicit user/);
  assert.equal(h.messages.length, 1);
}));

test('procedure start renders the raw request as an expandable pi-kit band', () => fixture(async resolver => {
  const h = host(resolver);
  const renderer = h.renderers.get('impeccable-procedure');
  assert.ok(renderer, 'message renderer registered');
  await h.command.handler('promote chosen preview', h.ctx);
  const [message] = h.messages[0];
  assert.equal(message.details.request, 'chosen preview');
  assert.deepEqual(message.details.loaded.map(entry => entry.id), ['promote']);
  const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text };
  const collapsed = renderer(message, { expanded: false, outputPad: 0 }, theme).render(80);
  assert.equal(collapsed.length, 3);
  assert.match(collapsed[1], /\[impeccable\] started \u00b7 chosen preview/);
  assert.ok(!collapsed.join('\n').includes('to expand'));
  assert.ok(!collapsed.join('\n').includes('# promote'));
  assert.ok(collapsed.every(line => visibleWidth(line) <= 80));
  const expanded = renderer(message, { expanded: true, outputPad: 0 }, theme).render(80);
  assert.deepEqual(expanded, collapsed);
}));

test('multi-intent freeform loads every matched bundle in one follow-up', async () => {
  const { resolver: realResolver } = await import('../src/resolver.ts');
  const { loadTriggers } = await import('../src/routing.ts');
  const sent = [], messages = [], commands = new Map(), renderers = new Map();
  const pi = { registerCommand: (id, command) => commands.set(id, command), registerTool: () => {}, sendUserMessage: (...args) => sent.push(args), sendMessage: (...args) => messages.push(args), registerMessageRenderer: (id, fn) => renderers.set(id, fn) };
  registerImpeccable(pi, realResolver, loadTriggers());
  const request = '运行全部检查，然后fix，直到满分';
  await commands.get('impeccable').handler(request, { hasUI: false, ui: { select: async () => undefined, notify() {} } });
  assert.equal(messages.length, 1);
  const [message] = messages[0];
  assert.deepEqual(message.details.loaded.map(entry => entry.id), ['audit', 'polish']);
  assert.equal(message.details.request, request);
  assert.ok(message.content.includes('Design Health Score') || message.content.includes('Audit Health Score'));
  assert.ok(message.content.includes('Triage and implement'));
  assert.match(message.content, /1\. \/impeccable audit — /);
  assert.match(message.content, /2\. \/impeccable polish — /);
  assert.equal(message.content.split('<impeccable-source id="setup">').length, 2);
  assert.equal(message.content.split('<impeccable-source id="accessibility">').length, 2);
  assert.ok(message.content.includes('--- Next capability: polish ---'));
  assert.ok(message.content.endsWith(request));
  const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text };
  const collapsed = renderers.get('impeccable-procedure')(message, { expanded: false, outputPad: 0 }, theme).render(80);
  assert.match(collapsed[1], /\[impeccable\] started \u00b7 运行全部检查，然后fix，直到满分/);
});

test('catalog rejects missing edges and required cycles, optional cycles terminate', () => fixture((resolver, root, entries) => {
  assert.throws(() => validateCatalog([...entries, { ...entries[0], id: 'bad', file: 'procedures/bad.md', requires: ['missing'] }]), /unknown catalog target/);
  const cyclic = entries.map(entry => entry.id === 'principles' ? { ...entry, requires: ['components'] } : entry);
  assert.throws(() => createResolver(root, cyclic), /[Cc]yclic/);
  const optional = entries.map(entry => entry.id === 'motion' ? { ...entry, discloses: [{ id: 'components', when: 'Controls apply' }] } : entry.id === 'components' ? { ...entry, discloses: [{ id: 'motion', when: 'Motion applies' }] } : entry);
  assert.deepEqual(createResolver(root, optional).load('polish', 'model', 'motion').loaded, ['motion']);
}));

test('resource symlinks cannot escape the package root', () => fixture((resolver, root) => {
  const outside = mkdtempSync(join(tmpdir(), 'impeccable outside '));
  try {
    writeFileSync(join(outside, 'secret.md'), 'not package content');
    rmSync(join(root, 'references/taste/motion.md'));
    symlinkSync(join(outside, 'secret.md'), join(root, 'references/taste/motion.md'));
    assert.throws(() => resolver.load('polish', 'model', 'motion'), /escapes package/);
  } finally { rmSync(outside, { recursive: true, force: true }); }
}));

test('registered renderer bounds details and leaves complete model guidance untouched', () => fixture(async (resolver, root) => {
  writeFileSync(join(root, 'references/taste/motion.md'), '# motion\n' + 'long guidance '.repeat(1000));
  const h = host(resolver);
  const result = await h.tool.execute('render', { capability: 'polish', reference: 'motion' });
  assert.ok(result.content[0].text.length > 10000);
  const theme = { fg: (_color, text) => text, bg: (_color, text) => text, bold: text => text };
  assert.equal(h.tool.renderShell, 'self');
  assert.deepEqual(h.tool.renderCall().render(20), []);
  for (const expanded of [false, true]) {
    const component = h.tool.renderResult(result, { expanded, isPartial: false }, theme, { isError: false });
    for (const width of [1, 20, 80]) {
      const lines = component.render(width);
      assert.ok(lines.every(line => visibleWidth(line) <= width));
      assert.ok(!lines.join(' ').includes('long guidance'));
    }
    // Four bounded `label · value` fields; at a wide width nothing wraps.
    assert.ok(component.render(80).length <= (expanded ? 7 : 3));
  }
}));
