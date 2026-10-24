#!/usr/bin/env python3
"""Run the configured real Codex or Pi host for one external evaluation case."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', choices=['codex', 'pi'])
    args = parser.parse_args()
    request = json.load(sys.stdin)
    cwd = Path(request['cwd']).resolve(strict=True)
    prompt = request['prompt']
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('An evaluation prompt is required')
    if args.host == 'codex':
        command = ['codex', 'exec', '--json', '--ephemeral', '--sandbox', 'workspace-write', '-c', 'approval_policy="never"', '-C', str(cwd), '-']
    else:
        command = ['pi', '--print', '--no-session']
    # The managed runner supplies auth, network policy and host settings. Keep
    # skills, hooks and project instructions enabled: they are under evaluation.
    return subprocess.run(command, cwd=cwd, input=prompt, text=True, check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
