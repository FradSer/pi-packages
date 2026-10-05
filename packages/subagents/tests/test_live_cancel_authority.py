"""Native Pi/RPC authority plus explicitly invented hosted-confirmation faults."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from native_support import NativeTui, records



# Every ownership fault runs through native print/RPC. TUI checks cancellation
# and its late diagnostic; ownership permutations do not change the renderer.
@pytest.mark.parametrize('interface,scenario', [
    ('print', 'stop-pending'), ('print', 'forged-successor'),
    ('print', 'late-control-failure'), ('print', 'reentrant-successor'),
    ('tui', 'stop-pending'), ('tui', 'late-control-failure'),
])
def test_native_controls_keep_exact_owner_after_cancellation(
    native_command: tuple, tmp_path: Path, interface: str, scenario: str,
) -> None:
    """The host's delayed/faulty return is synthetic; actual children and RPC are not."""
    command, env, snapshots, requests, release = native_command
    command = list(command)
    old = str(Path(__file__).resolve().parents[3] / 'tests' / 'live-agent-usage-fixture.ts')
    command[command.index(old)] = str(Path(__file__).resolve().parents[3] / 'tests' / 'live-cancel-authority-fixture.ts')
    env = {**env, 'PI_CANCEL_AUTHORITY_CASE': scenario}
    # Only late-control sends model input. Hold its response through inspect/stop
    # so an actual final answer cannot masquerade as the faulted control outcome.
    if scenario != 'late-control-failure':
        release.set()
    if interface == 'print':
        result = subprocess.run([*command, '--print'], cwd=tmp_path, env=env,
            input='', capture_output=True, text=True, timeout=35)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'NATIVE_AUTHORITY_DONE' in result.stdout, result.stdout + result.stderr
    else:
        tui = NativeTui(command, cwd=tmp_path, env=env, rows=35, columns=100, timeout=35)
        try:
            tui.wait_for(lambda: 'NATIVE_AUTHORITY_DONE' in tui.screen())
            assert '[agent] inspected' in tui.screen(), tui.screen()
            assert 'cancelled' in tui.screen(), tui.screen()
            tui.send(b'/quit\r')
            tui.wait_for(lambda: tui.process.poll() is not None)
            assert tui.process.returncode == 0
        finally:
            tui.close()
    events = records(snapshots)
    receipts = [event for event in events if event['kind'] == 'receipt']
    failures = [event for event in receipts if event['isError']]
    assert len(failures) == 1, receipts
    assert failures[0]['details']['code'] == 'cancelled', receipts
    assert failures[0]['details']['disposition'] == 'uncertain', receipts
    cancelled, = [event for event in events if event['kind'] == 'cancelled-native-control']
    assert cancelled['data']['code'] == 'cancelled' and cancelled['data']['disposition'] == 'uncertain', cancelled
    if scenario == 'reentrant-successor':
        assert 'session' not in cancelled['data'] and 'session' not in failures[0]['details']
    else:
        assert cancelled['data']['session'] == failures[0]['details']['session']
    if scenario == 'late-control-failure':
        # A cancelled input keeps its reservation with the runtime. The real
        # native dispatch is the correlated acknowledgement the host recorded.
        assert 'dispatched' not in cancelled['data'], cancelled
    else:
        assert cancelled['data']['dispatched'] is True, cancelled
    closes = [event for event in events if event['kind'] == 'native-close']
    assert all(event['outcome'] in ['closed', 'missing'] for event in closes), closes
    shutdown = events[-1]
    assert shutdown['kind'] == 'shutdown' and shutdown['living'] == 0, events
    assert all(child['pid'] > 1 for child in shutdown['children'])
    assert len(shutdown['children']) == (2 if scenario == 'forged-successor' else 1)
    assert [entry['owner'] for entry in shutdown['hostStops']] == (
        ['original', 'successor'] if scenario == 'forged-successor'
        else ['successor'] if scenario == 'reentrant-successor' else ['original'])
    if scenario == 'forged-successor':
        assert any(event['kind'] == 'successor-preserved' for event in events)
        assert len({entry['session'] for entry in shutdown['hostStops']}) == 2
    elif scenario == 'stop-pending':
        assert any(event['kind'] == 'late-confirmation-refused' for event in events)
    elif scenario == 'reentrant-successor':
        assert any(event['kind'] == 'synthetic-reentrant-start' for event in events)
        preserved, = [event for event in events if event['kind'] == 'reentrant-owner-preserved']
        assert shutdown['hostStops'][0]['session'] == preserved['session']
        assert any(event['kind'] == 'native-readiness' and event['owner'] == 'successor' and event['accepted'] for event in events)
    else:
        assert any(event['kind'] == 'native-input-ack' and event['accepted'] for event in events)
        assert any(event['kind'] == 'late-failure-readback' for event in events)
        inspected = next(event['details'] for event in receipts if event['details']['operation'] == 'agent_inspect')
        assert 'LATE_NATIVE_CONTROL_FAILURE' in inspected['sessions'][0]['error']
    assert len(requests) <= (1 if scenario == 'late-control-failure' else 0)
    assert not (tmp_path / 'agent' / 'agents').exists()
    assert not (tmp_path / 'agent' / 'subagent-sessions').exists()
