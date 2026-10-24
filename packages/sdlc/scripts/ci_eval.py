#!/usr/bin/env python3
"""Run a protected eval suite without requiring an active development task."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from sdlc import config, evaluate, snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cwd', type=Path)
    parser.add_argument('--output', type=Path, default=Path('/tmp/sdlc-eval-report.json'))
    args = parser.parse_args()
    cwd = args.cwd.resolve(strict=True)
    before = snapshot(cwd)
    try:
        cases = evaluate(cwd, config(cwd))
        report = {'passed': all(case['passed'] for case in cases) and before == snapshot(cwd), 'cases': cases, 'source': before}
    except Exception as error:
        report = {'passed': False, 'error': str(error), 'source': before}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
