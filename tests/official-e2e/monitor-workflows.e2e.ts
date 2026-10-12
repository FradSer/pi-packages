import { execFile } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { expect, test } from 'e2e';

const root = fileURLToPath(new URL('../../', import.meta.url));
const execute = promisify(execFile);
const quote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
const node = quote(process.execPath);
const compiler = quote(join(root, 'node_modules/typescript/bin/tsc'));

const workflows = [
  { name: 'confirms a successful project typecheck', status: 'success' },
  { name: 'returns located compiler errors for a failed verification', status: 'failure' },
  { name: 'rejects a success sentinel followed by a nonzero exit', status: 'failure' },
  { name: 'rejects malformed JSON completion', status: 'failure' },
  { name: 'reports a deadline after a success candidate', status: 'timeout' },
  { name: 'rejects a zero exit without its required result', status: 'result_missing' },
] as const;

for (const [index, workflow] of workflows.entries()) {
  // Given a finite verification, when actual Pi runs monitor_start, then the
  // original session receives the terminal outcome rather than a ready signal.
  test(`real Pi ${workflow.name}`, { timeout: 45_000, tags: ['monitor', 'verification'] }, async () => {
    const temporary = mkdtempSync(join(tmpdir(), 'pi-verification-e2e-'));
    mkdirSync(join(root, '.e2e'), { recursive: true });
    const evidence = mkdtempSync(join(root, '.e2e/native-monitor-'));
    try {
      const agent = join(temporary, 'agent');
      mkdirSync(agent, { mode: 0o700 });
      const invalid = join(temporary, 'invalid-verification.ts');
      writeFileSync(invalid, 'const value: number = "invalid type";\n');
      const commands = [
        `if ${node} ${compiler} --noEmit -p ${quote(join(root, 'tsconfig.extensions.json'))}; then printf 'FINAL {"ok":true}\\n'; else code=$?; printf 'FAILED {"ok":false,"exitCode":%s}\\n' "$code"; exit "$code"; fi`,
        `if ${node} ${compiler} --noEmit --strict --skipLibCheck ${quote(invalid)}; then printf 'FINAL {"ok":true}\\n'; else code=$?; printf 'FAILED {"ok":false,"exitCode":%s}\\n' "$code"; exit "$code"; fi`,
        `printf 'FINAL {"ok":true}\\n'; exit 7`,
        `printf 'FINAL {broken\\n'`,
        `${node} -e ${quote('console.log(\'FINAL {"ok":true}\'); setTimeout(() => {}, 10000)')}`,
        `printf 'verification produced no result\\n'`,
      ];
      const spec = {
        route: 'direct', expected: [workflow.status],
        jobs: [{ command: commands[index], description: workflow.name,
          result_pattern: '^FINAL (?<json>.*)$', failure_pattern: '^FAILED (?<json>.*)$',
          completion: 'exit', timeout_ms: index === 4 ? 1000 : 20_000 }],
      };
      const specPath = join(evidence, 'spec.json');
      const trace = join(evidence, 'events.jsonl');
      writeFileSync(specPath, JSON.stringify(spec, null, 2));
      const child = execute(process.execPath, [
        join(root, 'node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js'),
        '--offline', '-ne', '-ns', '-np', '-nc', '--no-session',
        '-e', join(root, 'packages/monitor/tests/transport-matrix-fixture.ts'),
        '--model', 'monitor-transport-offline/scripted', '--print', '--mode', 'json',
        'Run the finite verification and return its actual terminal outcome.',
      ], { cwd: temporary, env: { PATH: process.env.PATH ?? '', HOME: temporary,
        PI_CODING_AGENT_DIR: agent, PI_OFFLINE: '1', PI_TELEMETRY: '0',
        MONITOR_TRANSPORT_SPEC: specPath, MONITOR_TRANSPORT_TRACE: trace },
        timeout: 35_000, maxBuffer: 4 * 1024 * 1024 });
      child.child.stdin?.end();
      const result = await child.catch(error => {
        writeFileSync(join(evidence, 'pi.jsonl'), typeof error.stdout === 'string' ? error.stdout : '');
        writeFileSync(join(evidence, 'stderr.txt'), typeof error.stderr === 'string' ? error.stderr : '');
        throw error;
      });
      writeFileSync(join(evidence, 'pi.jsonl'), result.stdout);
      writeFileSync(join(evidence, 'stderr.txt'), result.stderr);
      const events = readFileSync(trace, 'utf8').trim().split('\n').map(line => JSON.parse(line));
      const terminals = events.filter(event => event.kind === 'tool_result' && event.event.toolName === 'monitor_start');
      const requests = events.filter(event => event.kind === 'request');
      expect(terminals).toHaveLength(1);
      expect(requests).toHaveLength(2);
      expect(events.indexOf(terminals[0])).toBeLessThan(events.indexOf(requests[1]));
      const terminal = terminals[0].event;
      const returned = requests[1].messages.filter((message: { role: string }) => message.role === 'toolResult');
      expect(returned).toHaveLength(1);
      expect(terminal.toolCallId).toBe('direct-0');
      expect(returned[0].toolCallId).toBe(terminal.toolCallId);
      expect(returned[0].toolName).toBe('monitor_start');
      expect(returned[0].details.monitorId).toBe(terminal.details.monitorId);
      expect(returned[0].details.result).toEqual(terminal.details.result);
      expect(terminal.details.result.status).toBe(workflow.status);
      expect(terminal.details.result.completion).toBe('exit');
      expect(terminal.details.monitorId).toBeTruthy();
      expect(events.filter(event => event.kind === 'send')).toHaveLength(0);
      expect(JSON.stringify(returned[0].content)).toContain(`status=${workflow.status}`);
      if (index === 0) expect(terminal.details.result.result).toEqual({ ok: true });
      if (index === 1) {
        expect(terminal.details.result.result.ok).toBe(false);
        expect(terminal.details.result.result.exitCode).toBeGreaterThan(0);
        expect(JSON.stringify(returned[0].content)).toContain('TS2322');
        expect(JSON.stringify(returned[0].content)).toContain('invalid-verification.ts');
      }
      if (index === 2 || index === 4) expect(terminal.details.result.output).toContain('[stdout] FINAL {"ok":true}');
      if (index === 2) {
        expect(terminal.details.result.exitCode).toBe(7);
        expect(terminal.details.result.reason).toBe('process_exit');
      }
      if (index === 3) expect(terminal.details.result.reason).toBe('invalid_json_result');
      if (index === 4) {
        expect(terminal.details.result.reason).toBe('timeout');
        expect(terminal.details.result.timeoutMs).toBe(1000);
      }
      if (index === 5) {
        expect(terminal.details.result.exitCode).toBe(0);
        expect(terminal.details.result.expected).toBe(spec.jobs[0].result_pattern);
      }
      const wire = result.stdout.trim().split('\n').map(line => JSON.parse(line));
      const starts = wire.filter(event => event.type === 'tool_execution_start' && event.toolName === 'monitor_start');
      expect(starts).toHaveLength(1);
      expect(starts[0].toolCallId).toBe(terminal.toolCallId);
      const final = wire.filter(event => event.type === 'message_end' && event.message.role === 'assistant' && event.message.stopReason === 'stop');
      expect(final).toHaveLength(1);
      expect(final[0].message.provider).toBe('monitor-transport-offline');
      expect(final[0].message.content).toEqual([{ type: 'text', text: 'TRANSPORT_MATRIX_READY' }]);
      expect(result.stderr).toBe('');
    } finally {
      rmSync(temporary, { recursive: true, force: true });
    }
  });
}
