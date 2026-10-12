import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test } from 'e2e';

const root = fileURLToPath(new URL('../../', import.meta.url));
const packages = readdirSync(join(root, 'packages')).flatMap((directory) => {
  const path = join(root, 'packages', directory);
  const manifest = JSON.parse(readFileSync(join(path, 'package.json'), 'utf8'));
  return manifest.pi || manifest.keywords?.includes('pi-package') ? [path] : [];
});

function audit(deadSource: boolean) {
  const temporary = mkdtempSync(join(tmpdir(), 'pi-installation-e2e-'));
  try {
    const sources = deadSource ? [...packages, join(temporary, 'missing-package')] : packages;
    const settings = join(temporary, 'settings.json');
    writeFileSync(settings, JSON.stringify({ packages: sources }));
    return spawnSync(process.execPath, [join(root, 'scripts/check-installation.mjs'), settings], {
      cwd: root,
      env: { PATH: process.env.PATH ?? '', HOME: temporary, PI_OFFLINE: '1' },
      encoding: 'utf8',
      timeout: 10_000,
    });
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

// Given isolated complete settings, when the real CLI runs, then its count and exit agree.
test('complete workspace settings pass the installation CLI', () => {
  const result = audit(false);
  expect(result.error).toBeUndefined();
  expect(result.status).toBe(0);
  expect(result.stdout).toContain(`OK: ${packages.length} workspace pi packages installed`);
  expect(result.stdout).toContain(`${packages.length} settings entries checked.`);
  expect(result.stderr).toBe('');
});

// Given a dead source, when the real CLI runs, then it rejects that exact settings entry.
test('dead package sources fail with a located diagnostic', () => {
  const result = audit(true);
  expect(result.error).toBeUndefined();
  expect(result.status).toBe(1);
  expect(result.stdout).toContain(`DEAD     settings.packages[${packages.length}]`);
  expect(result.stdout).not.toContain('OK:');
  expect(result.stderr).toBe('');
});
