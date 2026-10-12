import type { E2EConfig } from 'e2e';

// Official engine-less target: deterministic CLI checks, no model or custom adapter.
export default {
  projectId: 'fradser-pi-packages-cli',
  targets: [{ name: 'local-cli', platform: 'cli' }],
  agents: {},
  tests: ['tests/official-e2e/**/*.e2e.ts'],
  workers: 1,
  retries: 0,
  timeout: 15_000,
  output: '.e2e',
  reporters: ['list', 'junit', 'markdown'],
  trace: 'retain-on-failure',
} satisfies E2EConfig;
