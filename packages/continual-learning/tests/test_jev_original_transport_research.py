from support import isolated_run_bun


def test_original_transport_arms_and_endpoints_are_fixed() -> None:
    value = isolated_run_bun(r'''
      import {originalTransportArm,originalTransportEndpoint} from './packages/continual-learning/tests/jev-original-transport-research.ts';
      const ids=['direct-5s','proxy-15s','proxy-5s','direct-15s'];
      const arms=ids.map(originalTransportArm);
      const direct=originalTransportEndpoint(arms[0],undefined),proxy=originalTransportEndpoint(arms[1],'http://127.0.0.1:1234/jev');
      let invalidArm=false;try{originalTransportArm('direct-30s')}catch{invalidArm=true}
      const denied=['https://example.invalid/jev','http://localhost:1234/jev','http://127.0.0.1:1234/jev?token=x','http://127.0.0.1:0/jev'].map(u=>{try{originalTransportEndpoint(arms[1],u);return false}catch{return true}});
      console.log(JSON.stringify({arms,direct,proxy,invalidArm,denied}));
    ''')
    assert [v['timeout'] for v in value['arms']] == [5000, 15000, 5000, 15000]
    assert value['direct'] == 'https://api.typesafe.ai'
    assert value['proxy'] == 'http://127.0.0.1:1234/jev'
    assert value['invalidArm'] is True
    assert value['denied'] == [True] * 4


def test_original_transport_records_typed_numbers_without_source_text() -> None:
    value = isolated_run_bun(r'''
      import {originalTransportObservation} from './packages/continual-learning/tests/jev-original-transport-research.ts';
      const request={state:'PRIVATE ORIGINAL SOURCE',questions:{supported_0:{type:'noul',criteria:{true:'source',false:'source'}},expands_0:{type:'choice',criteria:{same:'source',narrower:'source',broader:'source',unclear:'source'}}}};
      const raw={model:'jev-1.13.0',answers:{supported_0:{type:'noul',noul:.99},expands_0:{type:'choice',choice:'same',confidence:.98,probabilities:{same:.985,narrower:.005,broader:.005,unclear:.005}}},usage:{input_tokens:123,output_tokens:45},extra:'PRIVATE RESPONSE'};
      const good=originalTransportObservation(request,raw);
      const bad=originalTransportObservation(request,{...raw,model:'jev-latest'});
      const invalid=originalTransportObservation(request,{...raw,answers:{...raw.answers,supported_0:{type:'noul',noul:2}}});
      console.log(JSON.stringify({good,bad,invalid,privateLeaked:JSON.stringify(good).includes('PRIVATE')}));
    ''')
    assert value['good']['valid'] is True
    assert value['good']['modelVerified'] is True
    assert value['good']['inputTokens'] == 123
    assert value['good']['outputTokens'] == 45
    assert len(value['good']['judgments']) == 2
    assert value['bad']['valid'] is False
    assert value['invalid']['valid'] is False
    assert value['privateLeaked'] is False


def test_original_transport_completion_requires_all_three_and_full_windows() -> None:
    value = isolated_run_bun(r'''
      import {originalTransportComplete} from './packages/continual-learning/tests/jev-original-transport-research.ts';
      const t={model:'jev-1.13.0',reason:'supported',requestCount:3,completedRequests:3,evidenceEntries:17,coveredEntries:17,evidenceWindows:2,completedWindows:2,inputTokens:100};
      const observations=Array.from({length:3},()=>({valid:true,modelVerified:true,inputTokens:1,outputTokens:1}));
      console.log(JSON.stringify({good:originalTransportComplete(t,observations),timeout:originalTransportComplete({...t,reason:'timeout'},observations),missing:originalTransportComplete({...t,coveredEntries:7},observations),wrongCount:originalTransportComplete({...t,requestCount:2,completedRequests:2},observations.slice(0,2))}));
    ''')
    assert value == {'good': True, 'timeout': False, 'missing': False, 'wrongCount': False}


def test_original_transport_budget_rejects_body_before_paid_send() -> None:
    value = isolated_run_bun(r'''
      import {originalTransportWireGuard} from './packages/continual-learning/tests/jev-original-transport-research.ts';
      const claim=originalTransportWireGuard(['a','b','c']);let external=0;
      const send=h=>{claim(h);external++};let drift=false,overflow=false;
      send('a');try{send('changed')}catch{drift=true}send('b');send('c');try{send('a')}catch{overflow=true}
      console.log(JSON.stringify({external,drift,overflow}));
    ''')
    assert value == {'external': 3, 'drift': True, 'overflow': True}


def test_original_transport_paid_guard_survives_optimized_python() -> None:
    import subprocess
    from pathlib import Path

    runner = Path(__file__).with_name('live_jev_original_transport.py')
    code = f"import sys;sys.path.insert(0,{str(runner.parent)!r});from live_jev_original_transport import require_paid_permission;require_paid_permission(False)"
    result = subprocess.run(['python3', '-O', '-c', code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert 'PermissionError' in result.stderr


def test_original_transport_timeout_stops_owned_group_and_retains_partials() -> None:
    import importlib.util
    import json
    import subprocess
    from pathlib import Path
    from unittest.mock import patch
    import tempfile

    file = Path(__file__).with_name('live_jev_original_transport.py')
    spec = importlib.util.spec_from_file_location('original_transport_timeout', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[tuple[int, int]] = []
    alive = True

    class Child:
        pid = 12345
        returncode = -15
        count = 0

        def communicate(self, timeout: int) -> tuple[bytes, bytes]:
            self.count += 1
            if self.count == 1:
                raise subprocess.TimeoutExpired('owned child', timeout, output=b'partial secret')
            return b'partial secret', b'error secret'

    with tempfile.TemporaryDirectory() as directory:
        prefix = Path(directory) / 'owned'
        def kill_group(pid: int, sig: int) -> None:
            nonlocal alive
            calls.append((pid, sig))
            if sig == 0 and not alive:
                raise ProcessLookupError()
            if sig != 0:
                alive = False

        with patch.object(module.subprocess, 'Popen', return_value=Child()), patch.object(module.os, 'killpg', side_effect=kill_group):
            result = module.run_owned_recorded(['owned'], env={}, timeout=1, prefix=prefix, secrets=['secret'])
        assert result['outcome'] == 'timeout'
        assert result['processGroupStopConfirmed'] is True
        assert calls[0][0] == 12345
        assert any(sig == module.signal.SIGTERM for _, sig in calls)
        assert b'secret' not in prefix.with_name('owned-stdout.txt').read_bytes()
        assert prefix.with_name('owned-stdout.txt').stat().st_mode & 0o777 == 0o600
        assert json.dumps(result).find('secret') == -1


def test_original_transport_full_collection_is_checked_before_any_send() -> None:
    value = isolated_run_bun(r'''
      import {verifyOriginalTransportWireSet} from './packages/continual-learning/tests/jev-original-transport-research.ts';
      let external=0,rejected=false;
      try{verifyOriginalTransportWireSet(['a','b','c'],['a','b','changed']);external+=3}catch{rejected=true}
      verifyOriginalTransportWireSet(['a','b','c'],['c','a','b']);
      console.log(JSON.stringify({external,rejected}));
    ''')
    assert value == {'external': 0, 'rejected': True}


def test_original_transport_normal_parent_exit_cleans_residual_group() -> None:
    import importlib.util
    from pathlib import Path
    from unittest.mock import patch
    import tempfile

    file = Path(__file__).with_name('live_jev_original_transport.py')
    spec = importlib.util.spec_from_file_location('original_transport_normal_exit', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sent: list[int] = []
    alive = True

    class Child:
        pid = 12345
        returncode = 0

        def communicate(self, timeout: int) -> tuple[bytes, bytes]:
            return b'completed', b''

    def kill_group(pid: int, sig: int) -> None:
        nonlocal alive
        if sig == 0:
            if not alive:
                raise ProcessLookupError()
        else:
            sent.append(sig)
            alive = False

    with tempfile.TemporaryDirectory() as directory:
        with patch.object(module.subprocess, 'Popen', return_value=Child()), patch.object(module.os, 'killpg', side_effect=kill_group):
            result = module.run_owned_recorded(['owned'], env={}, timeout=1, prefix=Path(directory) / 'owned', secrets=[])
        assert result['processGroupStopConfirmed'] is True
        assert sent


def test_original_transport_manifest_drift_blocks_before_arm_start() -> None:
    import importlib.util
    import hashlib
    from pathlib import Path
    from unittest.mock import patch
    import tempfile

    file = Path(__file__).with_name('live_jev_original_transport.py')
    spec = importlib.util.spec_from_file_location('original_transport_manifest_drift', file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        manifest = Path(directory) / 'manifest.json'
        manifest.write_bytes(b'original')
        expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
        manifest.write_bytes(b'changed')
        with patch.object(module, 'MANIFEST', manifest):
            refused = False
            try:
                module.verify({}, expected)
            except ValueError:
                refused = True
            assert refused


def test_original_transport_worker_exit_closes_blocked_local_upstream() -> None:
    import importlib.util
    import json
    import os
    import http.client
    import select
    import subprocess
    import sys
    from pathlib import Path
    import tempfile

    tests = Path(__file__).parent
    spec = importlib.util.spec_from_file_location('original_transport_worker_shutdown', tests / 'live_jev_original_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        prefix = Path(directory) / 'proxy'
        code = f'''
import sys, threading, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, {str(tests)!r})
import docker_experiment
class Handler(BaseHTTPRequestHandler):
 def log_message(self, *args): pass
 def do_POST(self):
  owner.requests += 1; owner.jev_requests += 1
  print(json.dumps({{"stage":"blocked-local-upstream"}}), flush=True)
  threading.Event().wait(30)
class Server(ThreadingHTTPServer):
 daemon_threads=True
 block_on_close=False
class FakeProxy:
 def __init__(self,*args,**kwargs):
  global owner
  owner=self
  self.server=Server(('127.0.0.1',0),Handler)
  self.token='fixture-token';self.counter_lock=threading.Lock()
  self.requests=0;self.jev_requests=0;self.errors=0;self.jev_usage=[]
 def __enter__(self):
  threading.Thread(target=self.server.serve_forever,daemon=True).start()
  return self
 def __exit__(self,*args):
  self.server.shutdown();self.server.server_close()
docker_experiment.InferenceProxy=FakeProxy
import jev_original_transport_proxy
sys.argv=['owned','--live',{str(prefix)!r},{directory!r}]
jev_original_transport_proxy.main()
'''
        child = subprocess.Popen([sys.executable, '-c', code], env={**os.environ, 'TYPESAFE_API_KEY': 'fixture-only'}, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        connection = None
        try:
            assert select.select([child.stdout], [], [], 5)[0]
            assert json.loads(child.stdout.readline())['stage'] == 'ready'
            ready = json.loads(prefix.with_name('proxy-proxy-ready.json').read_text())
            connection = http.client.HTTPConnection('127.0.0.1', ready['port'], timeout=5)
            connection.request('POST', '/jev/v1/systemone', body=b'{}')
            assert select.select([child.stdout], [], [], 5)[0]
            assert json.loads(child.stdout.readline())['stage'] == 'blocked-local-upstream'
            stopped = module.run_owned_recorded([], env={}, timeout=10, prefix=Path(directory) / 'worker', secrets=['fixture-token'], existing_child=child, input_data=b'stop\n')
            assert stopped['processGroupStopConfirmed'] is True
            final = json.loads(prefix.with_name('proxy-proxy-final.json').read_text())
            assert final['activeHandlersAtSnapshot'] == 1
            assert final['unknownLateUsagePossible'] is True
            assert final['remoteProviderWorkStoppedVerified'] is False
            closed = False
            try:
                connection.getresponse()
            except (OSError, http.client.RemoteDisconnected):
                closed = True
            assert closed
        finally:
            if connection:
                connection.close()
            if child.poll() is None:
                os.killpg(child.pid, 9)
                child.wait(timeout=5)
