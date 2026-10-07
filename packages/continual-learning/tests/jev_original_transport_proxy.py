"""Owned proxy process: unchanged forwarding, bounded lifetime and numeric snapshots."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any
from docker_experiment import InferenceProxy


def main() -> None:
    mode, prefix_text, root_text = sys.argv[1:]
    if mode not in ('--live', '--preflight-only'):
        raise ValueError('Explicit proxy mode required')
    live = mode == '--live'
    key = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if live and not key:
        raise PermissionError('Proxy credential unavailable')
    os.umask(0o077)
    prefix = Path(prefix_text)
    condition = threading.Condition()
    active = 0
    with InferenceProxy(Path(root_text), jev_key=key or 'fixture-only', request_budget=3) as proxy:
        original = proxy.server.RequestHandlerClass

        class TrackedHandler(original):
            def do_POST(self) -> None:
                nonlocal active
                if not live:
                    self.send_error(503, 'Offline proxy forbids upstream inference')
                    return
                if self.path != '/jev/v1/systemone':
                    self.send_error(404)
                    return
                with condition:
                    active += 1
                try:
                    super().do_POST()
                finally:
                    with condition:
                        active -= 1
                        condition.notify_all()

        proxy.server.RequestHandlerClass = TrackedHandler
        ready = {'pid': os.getpid(), 'token': proxy.token, 'port': proxy.server.server_address[1]}
        with prefix.with_name(prefix.name + '-proxy-ready.json').open('x') as file:
            json.dump(ready, file)
        print(json.dumps({'stage': 'ready'}), flush=True)
        for line in sys.stdin:
            if line.strip() == 'stop':
                break
        with condition:
            # A short bounded grace records already finishing handlers. Main
            # process exit closes every remaining owned socket/daemon thread.
            condition.wait_for(lambda: active == 0, timeout=1)
            with proxy.counter_lock:
                snapshot: dict[str, Any] = {'jevRequests': proxy.jev_requests, 'totalRequests': proxy.requests, 'providerErrors': proxy.errors, 'knownProxyUsage': list(proxy.jev_usage), 'activeHandlersAtSnapshot': active, 'upstreamSocketsClosedYet': False, 'remoteProviderWorkStoppedVerified': False, 'unknownLateUsagePossible': active > 0, 'accountBillingVerified': False}
        with prefix.with_name(prefix.name + '-proxy-final.json').open('x') as file:
            json.dump(snapshot, file, indent=2)
        print(json.dumps({'stage': 'stopping', 'activeHandlers': snapshot['activeHandlersAtSnapshot']}), flush=True)
    # The process now exits, including any original daemon handlers.


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'stage': 'failed', 'category': type(error).__name__}), flush=True)
        raise SystemExit(1)
