"""Public-only acceptance plans and bounded, durable subprocess observation."""
from __future__ import annotations
import json
from collections import deque
import os
import signal
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

REQUIREMENTS = {
    'ant-design__ant-design-54813': [
        'Button static semantic objects retain their existing root icon and content behavior',
        'Button classNames and styles functions receive merged runtime props and update after rerender',
        'useMergeSemantic concatenates same-key classes and merges same-key style objects without a schema',
        'useMergeSemantic maps schema defaults into nested keys while preserving explicit nested overrides',
    ],
    'stanfordnlp__dspy-8105': [
        'Synchronous callback instrumentation retains its existing behavior',
        'BaseLM async calls emit start and end callbacks with inputs outputs and errors',
        'Predict async calls emit start and end callbacks with inputs outputs and errors',
        'Program async calls emit start and end callbacks and preserve nested context across concurrent calls and exceptions',
    ],
}


def feature(task: str) -> str:
    return ('Feature: Public request acceptance\nScenario: Public requirements\nGiven the supplied draft\nWhen its observable behaviors are exercised\n' +
            ''.join(('Then ' if index == 1 else 'And ') + requirement + '\n'
                    for index, requirement in enumerate(REQUIREMENTS[task], 1)))



class Stagnation:
    """Stop consecutive identical observations; edits reset the observation window."""
    def __init__(self, limit: int = 6) -> None:
        self.limit = limit
        self.observations: deque[str] = deque(maxlen=limit * 3)

    def observe(self, event: dict[str, Any]) -> bool:
        if event.get('type') != 'tool_execution_end':
            return False
        if event.get('toolName') in {'edit', 'write'}:
            self.observations.clear()
            return False
        signature = json.dumps([event.get('toolName'), event.get('result')], sort_keys=True)
        self.observations.append(signature)
        return self.observations.count(signature) >= self.limit



def completed(exit_code: int, messages: list[dict[str, Any]]) -> bool:
    return exit_code == 0 and bool(messages) and messages[-1].get('stopReason') == 'stop'


def invoke(argv: list[str], seconds: float, prefix: Path,
           redact: Callable[[str], str]) -> tuple[str, str, int]:
    """Flush every complete JSON event before waiting; retain partial tails on timeout."""
    if seconds <= 0:
        return '', 'Shared budget exhausted before stage start', 124
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    buffers = {'stdout': b'', 'stderr': b''}
    chunks: dict[str, list[str]] = {'stdout': [], 'stderr': []}
    monitor = Stagnation()
    deadline = time.monotonic() + seconds
    stopped = None
    drain_deadline = float("inf")
    assert process.stdout is not None and process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
    selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
    with prefix.with_suffix('.jsonl').open('w') as log, prefix.with_suffix('.stderr').open('w') as errors:
        try:
            while selector.get_map():
                if time.monotonic() >= deadline and stopped is None:
                    stopped = 'shared_deadline'
                    os.killpg(process.pid, signal.SIGKILL)
                    drain_deadline = time.monotonic() + 2
                if time.monotonic() >= drain_deadline:
                    break
                for key, _ in selector.select(timeout=0.2):
                    data = key.fileobj.read1(65536)
                    stream = key.data
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[stream] += data
                    while b'\n' in buffers[stream]:
                        line, buffers[stream] = buffers[stream].split(b'\n', 1)
                        text = line.decode('utf8', errors='replace') + '\n'
                        chunks[stream].append(text)
                        destination = log if stream == 'stdout' else errors
                        destination.write(redact(text)); destination.flush()
                        if stream == 'stdout' and stopped is None:
                            try:
                                if monitor.observe(json.loads(text)):
                                    stopped = 'repeated_identical_observations'
                                    os.killpg(process.pid, signal.SIGKILL)
                                    drain_deadline = time.monotonic() + 2
                            except ValueError:
                                pass
            for stream, tail in buffers.items():
                text = tail.decode('utf8', errors='replace')
                chunks[stream].append(text)
                destination = log if stream == 'stdout' else errors
                destination.write(redact(text)); destination.flush()
            code = process.wait(timeout=5)
        finally:
            selector.close()
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
            process.stdout.close(); process.stderr.close()
    if stopped:
        prefix.with_suffix('.stop.json').write_text(json.dumps({'reason': stopped}))
    return ''.join(chunks['stdout']), ''.join(chunks['stderr']), 124 if stopped else code


def recovery(folder: Path) -> dict[str, Any]:
    """Resume one audited interrupted repair without restarting its completed review."""
    from postfix_protocol import review_text
    progress = json.loads((folder / 'progress.json').read_text())
    stages: list[list[dict[str, Any]]] = []
    for filename in ['stage-1.jsonl', 'stage-2.jsonl']:
        events = []
        for line in (folder / filename).read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        stages.append(events)
    review = review_text(stages[0])
    if review is None:
        raise ValueError('Recovery requires a completed review')
    observations = [event for event in stages[1] if event.get('type') == 'tool_execution_end'][-6:]
    return {'remainingRequests': max(0, 80 - int(progress['inferenceRequests']) - 1),
            'remainingSeconds': max(0, 1200 - float(progress['elapsedSeconds'])),
            'priorRequestsLowerBound': int(progress['inferenceRequests']),
            'priorElapsedSeconds': float(progress['elapsedSeconds']),
            'review': review, 'priorEvents': stages[0] + stages[1],
            'reviewEvents': stages[0],
            'context': json.dumps(observations, ensure_ascii=False)[-20000:]}
