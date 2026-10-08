import { observedAssert as assert, observeScenario, observedScenarios } from "../../../tests/e2e/support/assertion-observer.ts";
import { writeFileSync as writeObservationFile } from "node:fs";
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { GoalCore, GOAL_FOCUS_ENTRY } from '../src/core.ts';
import { registerGoalCommands } from '../src/commands.ts';
import { registerGoalTools } from '../src/tools.ts';

const results: string[] = [];
async function scenario(name: string, body: () => unknown) {
  try { await observeScenario(name, body); results.push(`ok ${name}`); }
  catch (error) { results.push(`FAIL ${name}: ${error}`); process.exitCode = 1; }
}
function fixture() {
  const cwd = mkdtempSync(join(tmpdir(), 'goal-thread-'));
  const sent: unknown[] = [], entries: unknown[] = [], notifications: string[] = [];
  const commands = new Map<string, { handler: Function }>();
  const tools = new Map<string, { execute: Function }>();
  const pi = { appendEntry: (_type: string, data: unknown) => entries.push(data), sendMessage: (...args: unknown[]) => sent.push(args),
    sendUserMessage: (text: string) => sent.push(text), registerCommand: (name: string, command: { handler: Function }) => commands.set(name, command),
    registerTool: (tool: { name: string; execute: Function }) => tools.set(tool.name, tool),
    getActiveTools: () => [], setActiveTools() {}, getAllTools: () => [] };
  let session = 'thread-a', branch: unknown[] = [];
  const ctx = { cwd, mode: 'print', hasUI: false, isIdle: () => true, hasPendingMessages: () => false,
    sessionManager: { getSessionId: () => session, getBranch: () => branch },
    ui: { notify: (text: string) => notifications.push(text), select: async (_label: string, options: string[]) => options[0], setWidget() {} } };
  const core = new GoalCore(pi as never, cwd);
  core.restore(ctx as never);
  return { core, ctx, commands, tools, sent, notifications,
    restore(id: string, goalId?: string) { session = id; branch = goalId ? [{ type: 'custom', customType: GOAL_FOCUS_ENTRY, data: { focusedGoalId: goalId } }] : []; core.restore(ctx as never); } };
}
await scenario('only /goal is registered and bare /goal never starts work', async () => {
  const f = fixture(); registerGoalCommands(f.core);
  assert.deepEqual([...f.commands.keys()], ['goal']);
  await f.commands.get('goal')!.handler('', f.ctx);
  assert.equal(f.sent.length, 1);
  assert.match(JSON.stringify(f.sent), /no active goal/);
  f.core.shutdown();
});
await scenario('resume acquires this thread and delivers one authorized continuation', async () => {
  const f = fixture();
  const created = f.core.store.create({ id: 'goal-resume', owner: 'old-process', objective: 'Verify export.' });
  assert.ok(created.ok);
  f.core.store.apply({ expectedGoalId: 'goal-resume', mutate: g => { delete g.threadId; return g; } });
  f.restore('thread-a', 'goal-resume');
  assert.equal(f.core.scheduler.resume(f.core.goal!, {}, "user"), true);
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(f.sent.length, 1, 'resume must deliver, not just report success');
  assert.equal(f.core.goal?.scheduler?.owner, 'thread-a');
  assert.equal(f.core.goal?.scheduler?.used, 1);
  f.restore('thread-b');
  assert.equal(f.core.goal, undefined);
  f.core.shutdown();
});
await scenario('all surfaces read fresh state and paused work consumes no usage', () => {
  const f = fixture();
  f.core.store.create({ id: 'goal-fresh', owner: 'thread-a', objective: 'Verify export.' });
  f.restore('thread-a', 'goal-fresh');
  assert.equal(f.core.goal?.status, 'active');
  const other = new (f.core.store.constructor as typeof import('../src/store.ts').GoalStore)({ projectRoot: f.ctx.cwd });
  other.apply({ expectedGoalId: 'goal-fresh', mutate: g => ({ ...g, status: 'paused', autoContinue: false }) });
  assert.equal(f.core.goal?.status, 'paused');
  f.core.chargeUsage(f.ctx as never, f.core.goal!, 1, 100, 1);
  assert.equal(f.core.goal?.usage.tokensUsed, 0);
  f.core.shutdown();
});
await scenario('thread ownership, exact actions, pause and clear remain consistent', async () => {
  const f = fixture(); registerGoalCommands(f.core);
  const handler = f.commands.get('goal')!.handler;
  const seed = '全面优化 packages/matt-pocock，基于 Pi v1.0。\n完成条件：包测试、typecheck、打包检查和真实 Pi 离线交互验证通过。\n不发布、不提交、不修改其他包。';
  await handler(seed, f.ctx);
  assert.ok(String(((f.sent[0] as unknown as [{ content: string }])[0] as { content: string }).content).includes(seed), 'preserve multiline acceptance and boundaries');
  await handler('clear my schedule', f.ctx);
  assert.ok(String(((f.sent[1] as unknown as [{ content: string }])[0] as { content: string }).content).includes('clear my schedule'));
  f.core.store.create({ id: 'owned', owner: 'thread-a', objective: 'Owned goal.' });
  f.restore('thread-a', 'owned');
  await handler('pause', f.ctx);
  assert.equal(f.core.goal?.status, 'paused');
  const before = f.core.goal!.usage.tokensUsed;
  f.core.chargeUsage(f.ctx as never, f.core.goal!, 8, 999, 5);
  assert.equal(f.core.goal!.usage.tokensUsed, before);
  await handler('', f.ctx);
  assert.match(JSON.stringify(f.sent.at(-1)), /paused/);
  f.restore('thread-b', 'owned');
  assert.equal(f.core.goal, undefined, 'even a copied entry cannot attach an owned goal');
  await handler('resume', f.ctx);
  assert.match(JSON.stringify(f.sent.at(-1)), /no active goal/);
  f.restore('thread-a', 'owned');
  f.ctx.hasUI = true;
  await handler('clear', f.ctx);
  assert.equal(f.core.goal, undefined);
  assert.equal(Boolean(f.core.store.readGoal('owned')), false);
  assert.equal(f.core.scheduler.isArmed(), false);
  f.core.shutdown();
});

await scenario('explicit goal text activates revision but ordinary edits preserve pause', async () => {
  const f = fixture(); registerGoalCommands(f.core); registerGoalTools(f.core);
  f.core.store.create({ id: 'revised', owner: 'thread-a', objective: 'Old goal.' });
  f.restore('thread-a', 'revised');
  f.core.scheduler.pause(f.core.goal!, 'Paused', 'user');
  const edit = (objective: string) => f.tools.get('update_goal')!.execute('edit', { objective }, undefined, undefined, f.ctx);
  await edit('Plain edit.');
  assert.equal(f.core.goal?.status, 'paused');
  await f.commands.get('goal')!.handler('New goal. Completion: E2E passes.', f.ctx);
  f.core.acceptGoalSetting(((f.sent.at(-1) as unknown as [{ content: string }])[0].content) as string);
  await edit('New goal with E2E acceptance.');
  assert.equal(f.core.goal?.status, 'active', 'the explicit setting request activates its successful revision');
  assert.ok(f.core.scheduler.isArmed());
  // Two actors resume a goal, and the ledger has to tell them apart: the user
  // typed `/goal <text>` and the model revised, which is not the user typing
  // `/goal resume`.
  f.core.scheduler.pause(f.core.goal!, 'Paused again', 'user');
  await f.commands.get('goal')!.handler('An abandoned request.', f.ctx);
  // delivered row would accept via message_start in production; restore drops it like a boundary
  f.restore('thread-a', 'revised');
  await edit('Edit after a session boundary.');
  assert.equal(f.core.goal?.status, 'paused', 'a boundary drops activation intent');
  f.core.shutdown();
});

await scenario('rejected busy or failed delivery cannot activate an unrelated paused edit', async () => {
  for (const mode of ['busy', 'pending', 'throw']) {
    const f = fixture(); registerGoalCommands(f.core); registerGoalTools(f.core);
    f.core.store.create({ id: 'rejected', owner: 'thread-a', objective: 'Old goal.' });
    f.restore('thread-a', 'rejected');
    f.core.scheduler.pause(f.core.goal!, 'Paused', 'user');
    f.ctx.isIdle = () => mode !== 'busy';
    f.ctx.hasPendingMessages = () => mode === 'pending';
    if (mode === 'throw') f.core.pi.sendMessage = () => { throw new Error('Agent is already processing.'); };
    try { await f.commands.get('goal')!.handler('Rejected request.', f.ctx); } catch { /* native host rejection */ }
    await f.tools.get('update_goal')!.execute('old-edit', { objective: 'Unrelated internal edit.' }, undefined, undefined, f.ctx);
    assert.equal(f.core.goal?.status, 'paused', mode);
    assert.equal(f.core.scheduler.isArmed(), false, mode);
    assert.equal(f.sent.length, mode === 'throw' ? 0 : 1, mode);
    f.core.shutdown();
  }
});
await scenario('an explicit old completion verdict cannot release a resumed generation', async () => {
  const f = fixture(); registerGoalCommands(f.core); registerGoalTools(f.core);
  let release!: (value: { met: boolean; report: string }) => void;
  (f.core as unknown as { runCheck: Function }).runCheck = () => new Promise(resolve => { release = resolve; });
  f.core.store.create({ id: 'explicit-race', owner: 'thread-a', objective: 'Race goal.' });
  f.restore('thread-a', 'explicit-race');
  const completion = f.tools.get('update_goal')!.execute('complete', { status: 'complete', completion_summary: 'Old claim.' }, undefined, undefined, f.ctx);
  await f.commands.get('goal')!.handler('resume', f.ctx);
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(f.sent.length, 2);
  const resumedScheduler = structuredClone(f.core.goal?.scheduler);
  release({ met: true, report: 'Old MET.' });
  await completion;
  assert.ok(f.core.goal, 'resumed goal must remain open');
  assert.equal(f.core.goal?.status, 'active');
  assert.deepEqual(f.core.goal?.scheduler, resumedScheduler, 'the stale verdict preserves the resumed dispatch and generation');
  f.core.shutdown();
});
await scenario('a void send rejected asynchronously grants no later activation', async () => {
  const f = fixture(); registerGoalCommands(f.core); registerGoalTools(f.core);
  f.core.store.create({ id: 'async-rejected', owner: 'thread-a', objective: 'Paused goal.' });
  f.restore('thread-a', 'async-rejected');
  f.core.scheduler.pause(f.core.goal!, 'Paused', 'user');
  // Pi's extension send returns void even when its asynchronous preflight fails.
  f.core.pi.sendMessage = (...args: unknown[]) => { (f.sent as unknown[]).push(args); };
  await f.commands.get('goal')!.handler('Never delivered.', f.ctx);
  await f.tools.get('update_goal')!.execute('unrelated', { objective: 'Unrelated old edit.' }, undefined, undefined, f.ctx);
  assert.equal(f.core.goal?.status, 'paused');
  assert.equal(f.core.scheduler.isArmed(), false);
  f.core.shutdown();
});
console.log(JSON.stringify(results));

if (process.env.PI_E2E_ASSERTION_PATH) writeObservationFile(process.env.PI_E2E_ASSERTION_PATH, JSON.stringify(observedScenarios()));
