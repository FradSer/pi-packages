"""The reliability probe must retain timeout output, not erase its failure."""
import subprocess
import sys
import json
import os
import signal
import live_agents_reliability as probe


def test_timeout_reaps_process_group_and_retains_both_streams():
    child=subprocess.Popen([sys.executable,'-u','-c',
        'import sys,signal; print("ready",flush=True); print("before-timeout",file=sys.stderr,flush=True); signal.pause()'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        assert child.stdout.readline()==b'ready\n'
        code,stdout,stderr,timed_out=probe.communicate_bounded(child,0.05)
        assert code==124 and timed_out
        assert b'before-timeout' in stderr
        assert child.poll() is not None
    finally:
        if child.poll() is None: child.kill();child.wait()


def test_timeout_stops_recorded_detached_planner(tmp_path):
    registry=tmp_path/'children.jsonl'
    script='''import subprocess,sys,json,signal
c=subprocess.Popen([sys.executable,'-c','import signal; signal.pause()'],start_new_session=True)
open(sys.argv[1],'w').write(json.dumps({'pid':c.pid,'event':'started'})+'\\n')
print('ready',flush=True)
signal.pause()
'''
    parent=subprocess.Popen([sys.executable,'-u','-c',script,str(registry)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    pid=None
    try:
        assert parent.stdout.readline()==b'ready\n'
        pid=json.loads(registry.read_text())['pid']
        code,_,_,timed_out=probe.communicate_bounded(parent,0.05,registry)
        assert code==124 and timed_out
        # A zombie has stopped executing; its OS parent owns final reaping.
        state=subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
        assert not state or state.startswith('Z')
    finally:
        if parent.poll() is None: parent.kill();parent.wait()
        if pid:
            probe.terminate_recorded_groups(registry)


def test_permission_failure_is_ignored_only_for_observed_stopped_groups(tmp_path, monkeypatch):
    """Given a denied signal, When cleanup checks the group, Then live/unknown still fail."""
    import pytest
    registry = tmp_path / 'children.jsonl'
    registry.write_text(json.dumps({'pid': 12345, 'event': 'started'}) + '\n')
    def denied(*_args):
        raise PermissionError('denied')
    monkeypatch.setattr(probe.os, 'killpg', denied)
    for status, output, stopped in [(0, '', True), (0, '12345 Z\n', True),
                                    (0, '12345 Z\n12345 S\n', False),
                                    (1, '', False), (0, 'malformed', False)]:
        monkeypatch.setattr(probe.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a, status, output, ''))
        if stopped:
            probe.terminate_recorded_groups(registry)
        else:
            with pytest.raises(PermissionError):
                probe.terminate_recorded_groups(registry)
