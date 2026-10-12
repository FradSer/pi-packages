import { execFile, type PromiseWithChild } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { expect, test } from 'e2e';

const root = fileURLToPath(new URL('../../', import.meta.url));
const execute = promisify(execFile);

async function retainPiOutput(child: PromiseWithChild<{ stdout: string; stderr: string }>, evidence: string) {
  child.child.stdin?.end();
  try {
    const result = await child;
    writeFileSync(join(evidence, 'pi.jsonl'), result.stdout);
    writeFileSync(join(evidence, 'stderr.txt'), result.stderr);
    return result;
  } catch (error) {
    const stdout = error && typeof error === 'object' && 'stdout' in error && typeof error.stdout === 'string' ? error.stdout : '';
    const stderr = error && typeof error === 'object' && 'stderr' in error && typeof error.stderr === 'string' ? error.stderr : '';
    writeFileSync(join(evidence, 'pi.jsonl'), stdout);
    writeFileSync(join(evidence, 'stderr.txt'), stderr);
    throw error;
  }
}

// Given isolated Pi + the existing local provider, when its monitor runs a real
// child, then the terminal result returns to the original session exactly once.
test('real Pi delivers its monitored child result to the original session', { timeout: 45_000 }, async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'pi-monitor-e2e-'));
  mkdirSync(join(root, '.e2e'), { recursive: true });
  const evidence = mkdtempSync(join(root, '.e2e/native-monitor-'));
  const trace = join(evidence, 'events.jsonl');
  try {
    const agent = join(temporary, 'agent');
    mkdirSync(agent, { mode: 0o700 });
    const child = execute(process.execPath, [
      join(root, 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
      '--offline', '-ne', '-ns', '-np', '-nc', '--no-session',
      '-e', join(root, 'packages/monitor/tests/native-fixture.ts'),
      '--model', 'monitor-offline/scripted', '--print', '--mode', 'json',
      'Verify offline monitor.',
    ], {
      cwd: temporary,
      env: {
        PATH: process.env.PATH ?? '', HOME: temporary,
        PI_CODING_AGENT_DIR: agent, PI_OFFLINE: '1', PI_TELEMETRY: '0',
        PI_MONITOR_NATIVE_TRACE: trace, PI_MONITOR_NATIVE_CASE: 'standalone',
      },
      timeout: 35_000,
      maxBuffer: 4 * 1024 * 1024,
    });
    // Pi reads piped stdin before starting; explicitly finish the empty input.
    const { stdout, stderr } = await retainPiOutput(child, evidence);
    const events = readFileSync(trace, 'utf8').trim().split('\n').map((line) => JSON.parse(line));
    const requests = events.filter((event) => event.kind === 'request');
    const terminals = events.filter((event) => event.kind === 'tool_result' && event.event.toolName === 'monitor_start');
    const sends = events.filter((event) => event.kind === 'send' && event.message.customType === 'monitor-result');
    expect(requests).toHaveLength(2);
    expect(terminals).toHaveLength(1);
    expect(sends).toHaveLength(0); // Headless Pi returns directly, without a duplicate wake.
    const terminal = terminals[0];
    expect(terminal.event.details.monitorId).toBeTruthy();
    expect(terminal.event.details.result.status).toBe('success');
    expect(terminal.event.details.result.matched).toBe('DONE_NATIVE');
    expect(requests[1].at).toBeGreaterThanOrEqual(terminal.at);
    const returned = requests[1].messages.filter((message: { role: string }) => message.role === 'toolResult');
    expect(returned).toHaveLength(1);
    expect(returned[0].toolName).toBe('monitor_start');
    if (typeof terminal.event.toolCallId !== 'string' || !terminal.event.toolCallId.trim()) throw new Error('Nonempty terminal toolCallId is required');
    expect(returned[0].toolCallId).toBe(terminal.event.toolCallId);
    expect(JSON.stringify(returned[0].content)).toContain('DONE_NATIVE');
    expect(JSON.stringify(returned.map((message: { content: unknown }) => message.content))).not.toContain('PRIVATE_PROGRESS');
    expect(requests[1].activeTools).not.toContain('monitor_stop');
    expect(requests[1].activeTools).toContain('fixture_foreign');
    const wire = stdout.trim().split('\n').map((line) => JSON.parse(line));
    const starts = wire.filter((event) => event.type === 'tool_execution_start' && event.toolName === 'monitor_start');
    expect(starts).toHaveLength(1);
    expect(starts[0].toolCallId).toBe(terminal.event.toolCallId);
    const final = wire.filter((event) => event.type === 'message_end' && event.message.role === 'assistant' && event.message.stopReason === 'stop');
    expect(final).toHaveLength(1);
    expect(final[0].message.provider).toBe('monitor-offline');
    expect(final[0].message.content).toEqual([{ type: 'text', text: 'MONITOR_NATIVE_READY' }]);
    expect(stderr).toBe('');
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
});

// Given a CLI startup failure, when Pi rejects the provider, then its raw
// diagnostics survive without invoking a model or keeping temporary settings.
test('real Pi startup failures retain subprocess diagnostics', async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'pi-monitor-e2e-failure-'));
  mkdirSync(join(root, '.e2e'), { recursive: true });
  const evidence = mkdtempSync(join(root, '.e2e/native-monitor-'));
  let failed = false;
  try {
    const child = execute(process.execPath, [
      join(root, 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
      '--offline', '-ne', '-ns', '-np', '-nc', '--no-session', '--no-tools',
      '--provider', 'offline-e2e-missing-provider', '--model', 'missing', '--print', 'Never call a model.',
    ], { cwd: temporary, env: { PATH: process.env.PATH ?? '', HOME: temporary, PI_CODING_AGENT_DIR: join(temporary, 'agent'), PI_OFFLINE: '1', PI_TELEMETRY: '0' }, timeout: 10_000 });
    try { await retainPiOutput(child, evidence); } catch { failed = true; }
    expect(failed).toBe(true);
    expect(existsSync(join(evidence, 'pi.jsonl'))).toBe(true);
    expect(readFileSync(join(evidence, 'stderr.txt'), 'utf8')).toContain('offline-e2e-missing-provider');
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  expect(existsSync(temporary)).toBe(false);
});
