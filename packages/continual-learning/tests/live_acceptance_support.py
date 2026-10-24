"""Shared, credential-free isolation and evidence plumbing for live acceptance."""
from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
from urllib.parse import urlparse

ENV_KEYS = frozenset({'PATH', 'LANG', 'LC_ALL', 'HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'PI_CODING_AGENT_DIR', 'PI_TELEMETRY', 'TERM', 'PI_OFFLINE'})


def isolated_environment(base: Path, agent: Path) -> dict[str, str]:
    return {**{key: value for key, value in os.environ.items() if key in {'PATH', 'LANG', 'LC_ALL'}},
            'HOME': str(base), 'XDG_CONFIG_HOME': str(base / 'xdg-config'),
            'XDG_DATA_HOME': str(base / 'xdg-data'), 'XDG_STATE_HOME': str(base / 'xdg-state'),
            'PI_CODING_AGENT_DIR': str(agent), 'PI_TELEMETRY': '0', 'TERM': 'xterm-256color', 'PI_OFFLINE': '1'}


def preflight(base: Path, project: Path, agent: Path, env: dict[str, str], *, real_model: bool) -> dict:
    assert not set(env) - ENV_KEYS, 'Unexpected inherited service environment'
    for path in (project, agent):
        assert path.resolve().is_relative_to(base.resolve()) and path.resolve() != base.resolve(), 'Root is not disposable'
        assert not path.is_symlink(), 'Root is a symlink'
    assert Path(env['HOME']).resolve() == base.resolve(), 'HOME is not isolated'
    assert Path(env['PI_CODING_AGENT_DIR']).resolve() == agent.resolve(), 'Agent is not isolated'
    assert json.loads((agent / 'continual-learning.json').read_text()).get('jev') is False, 'Jev must be explicitly disabled'
    model = json.loads((agent / 'memory.json').read_text())
    assert all(isinstance(model.get(key), str) and model[key] for key in ('provider', 'model')), 'Missing explicit provider/model'
    models_file = agent / 'models.json'
    providers = json.loads(models_file.read_text()).get('providers', {}) if models_file.exists() else {}
    provider = providers.get(model['provider'], {})
    if not real_model:
        url = urlparse(provider.get('baseUrl', ''))
        assert url.scheme == 'http' and url.hostname == '127.0.0.1' and url.port, 'Offline provider must be explicit loopback'
        assert not (agent / 'auth.json').exists(), 'Offline run must not contain real auth'
    for name in ('auth.json', 'models.json'):
        file = agent / name
        if real_model and file.exists():
            assert file.stat().st_mode & 0o077 == 0, 'Private provider file permissions required'
    return {'mode': 'real-model' if real_model else 'loopback', 'provider': model['provider'], 'model': model['model'],
            'homeIsolated': True, 'agentIsolated': True, 'jevEnabled': False, 'environmentKeys': sorted(env),
            'networkEvidence': 'provider configuration; not packet capture or OS network confinement'}


def dialog_result(events: list[dict], start: int, dialog_id: int, value: bool) -> bool:
    return any(row.get('kind') == 'confirmed' and row.get('dialogId') == dialog_id and row.get('value') is value for row in events[start:])


class EvidenceRun:
    def __init__(self, parent: Path, sources: dict[str, Path]) -> None:
        parent.mkdir(parents=True, exist_ok=True)
        self.output = parent / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12])
        self.output.mkdir(mode=0o700)
        self.sources = sources
        self.start_hashes = self.hashes()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.write('source-start.json', json.dumps(self.start_hashes, indent=2))

    def hashes(self) -> dict[str, str]:
        return {name: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'absent' for name, path in self.sources.items()}

    def write(self, name: str, value: str) -> None:
        (self.output / name).write_text(value)

    def verify_sources(self) -> None:
        assert self.hashes() == self.start_hashes, 'Acceptance source changed during this run'

    def finish(self, report: dict) -> dict:
        report.update({'outputDir': str(self.output), 'startedAt': self.started_at,
                       'finishedAt': datetime.now(timezone.utc).isoformat(), 'sourceHashes': self.start_hashes,
                       'sourceHashesAfter': self.hashes()})
        try:
            self.verify_sources()
            report['sourceUnchanged'] = True
        except AssertionError as error:
            report.update({'status': 'failed', 'sourceUnchanged': False, 'error': str(error)})
        self.write('manifest.json', json.dumps(report, indent=2, ensure_ascii=False))
        snapshots = self.output / 'snapshots.json'
        lines = ['# 学习与撤销验收', '', f"状态：{report.get('status', 'failed')}。", '',
                 '图片为实际 Pi PTY 字节重建，不是系统截图。每轮保存在独立目录。', '',
                 '真实模型模式验证 Memory；默认 loopback 模式验证 Memory 与 Harness。Jev 关闭；网络声明基于配置，不代表网络抓包或操作系统网络隔离。', '']
        if report.get('error'):
            lines += ['验收失败，详情见 manifest.json。失败不会被受控模型通过覆盖。', '']
        if snapshots.exists():
            value = json.loads(snapshots.read_text())
            lines += ['| 文件 | 学习前 | 学习后 | 撤销后 |', '|---|---|---|---|']
            for name in sorted(set().union(*(set(stage or {}) for stage in value.values()))):
                def state(stage: str) -> str:
                    if value[stage] is None: return '未采集'
                    entry = value[stage].get(name)
                    return '不存在' if entry is None else f"{entry['sha256'][:12]} / {oct(entry['mode'])}"
                lines.append(f"| {name} | {state('before')} | {state('learned')} | {state('after')} |")
            lines.append('')
        for capture in report.get('captures', []):
            lines += [f"## {capture['name']} ({capture['columns']}×{capture['rows']})", '',
                      f"![PTY reconstruction]({self.output / (capture['name'] + '.png')})", '']
        lines += [' · '.join(f'[{label}]({self.output / name})' for label, name in [('Manifest', 'manifest.json'), ('回执', 'receipt.json'), ('文件快照', 'snapshots.json'), ('交互事件', 'events.jsonl')] if (self.output / name).exists()), '']
        self.write('gallery.zh-CN.md', '\n'.join(lines))
        return report


def private_provider_copy(source: Path, agent: Path, provider: str) -> list[bytes]:
    """Copy only the selected provider; return secret bytes for evidence checks."""
    secrets: list[bytes] = []
    def collect(value: object, key: str = '') -> None:
        if isinstance(value, dict):
            for name, child in value.items(): collect(child, name)
        elif isinstance(value, list):
            for child in value: collect(child, key)
        elif isinstance(value, str) and len(value) >= 8 and any(part in key.lower() for part in ('key', 'token', 'secret', 'access', 'refresh', 'password', 'authorization')):
            secrets.append(value.encode())
    for name in ('models.json', 'auth.json'):
        file = source / name
        if not file.is_file(): continue
        original = json.loads(file.read_text())
        if name == 'models.json':
            selected = original.get('providers', {}).get(provider)
            if selected is None: continue
            value = {'providers': {provider: selected}}
        else:
            if provider not in original: continue
            value = {provider: original[provider]}
        collect(value)
        target = agent / name
        with open(target, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
            json.dump(value, stream)
        target.chmod(0o600)
    return secrets


def archive_terminal(transcript: bytes, events: Path, output: Path, validate: Callable[[bytes], bytes], close: Callable[[], None]) -> None:
    try:
        terminal = validate(transcript)
        event_bytes = validate(events.read_bytes()) if events.exists() else None
        (output / 'terminal.ansi').write_bytes(terminal)
        if event_bytes is not None:
            (output / 'events.jsonl').write_bytes(event_bytes)
    finally:
        close()


def workspace_pi(repo: Path) -> str:
    """Use the installed workspace CLI so global upgrades cannot change proof."""
    command = repo / 'node_modules/.bin/pi'
    if not command.is_file() or not os.access(command, os.X_OK):
        raise AssertionError('Workspace Pi CLI is unavailable; install workspace dependencies first')
    return str(command)


def workspace_pnpm(repo: Path) -> str:
    """Find the already installed pinned CLI without executing Corepack."""
    manager = json.loads((repo / 'package.json').read_text()).get('packageManager', '')
    assert manager.startswith('pnpm@'), 'Workspace does not pin pnpm'
    version = manager[len('pnpm@'):].split('+', 1)[0]
    candidates = [repo / 'node_modules/pnpm/package.json']
    command = shutil.which('pnpm')
    if command:
        candidates.append(Path(command).resolve().parent.parent / 'package.json')
    cache = os.environ.get('COREPACK_HOME')
    if not cache:
        base = os.environ.get('XDG_CACHE_HOME') or os.environ.get('LOCALAPPDATA') or str(Path.home() / '.cache')
        cache = str(Path(base) / 'node/corepack')
    candidates.append(Path(cache) / 'v1/pnpm' / version / 'package.json')
    for manifest in candidates:
        if not manifest.is_file():
            continue
        package = json.loads(manifest.read_text())
        if package.get('name') != 'pnpm' or package.get('version') != version:
            continue
        bins = package.get('bin', {})
        relative = bins.get('pnpm') if isinstance(bins, dict) else bins
        if not isinstance(relative, str):
            continue
        cli = manifest.parent / relative
        if cli.is_file():
            return str(cli.resolve())
    raise AssertionError(f'Installed workspace pnpm {version} CLI is unavailable; no download attempted')
