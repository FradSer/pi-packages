"""Audit retained native pairs; never substitute candidate or mock evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from live_jev_workflow import workflow_matrix_gate, workflow_improvement_gate


def resources(run: dict[str, Any]) -> dict[str, Any]:
    receipts = run['receipts']
    judgments = [attempt['jev'] for receipt in receipts for attempt in receipt.get('attempts', []) if 'jev' in attempt]
    returned = [judgment for judgment in judgments if isinstance(judgment.get('inputTokens'), int)]
    effects = {key: value for key, value in run['checks'].items() if key != 'implementationStable'}
    return {
        'effectsPassed': sum(effects.values()), 'effectsTotal': len(effects),
        'durationSeconds': run['durationSeconds'],
        'pipelineWorkerCostUsd': sum(receipt['totals']['cost'] for receipt in receipts),
        'workerCostAvailable': all(receipt.get('costAvailable') is True for receipt in receipts),
        'pipelineWorkerTokens': sum(receipt['totals']['totalTokens'] for receipt in receipts),
        'returnedJevJudgments': len(returned),
        'jevModelVersions': sorted({judgment['model'] for judgment in returned}),
        'jevInputTokens': sum(judgment['inputTokens'] for judgment in returned),
        'jevOutputTokens': sum(judgment.get('outputTokens', 0) for judgment in returned),
        'jevJudgmentMs': sum(judgment.get('durationMs', 0) for judgment in judgments),
        'estimatedJevCostUsd': sum(judgment.get('estimatedCostUsd', 0) for judgment in returned),
        'judgmentsWithoutUsage': sum(judgment.get('status') != 'disabled' and judgment.get('reason') in ('timeout', 'unavailable', 'invalid-response') and 'inputTokens' not in judgment for judgment in judgments),
        'phaseOutcomes': [[(attempt['phase'], attempt['outcome']) for attempt in receipt.get('attempts', [])] for receipt in receipts],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('pairs', nargs=4, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    reports = [json.loads(file.read_text()) for file in args.pairs]
    audit = workflow_matrix_gate(reports)
    audit.update(evidence='audit-of-retained-real-native-pairs', costScope='Two learning passes only; source/fresh-session generation excluded. Jev costs are tariff estimates, not invoices. Missing usage is unknown.',
                 artifacts=[file.name for file in args.pairs],
                 resources={report['runs'][0]['scenario']: {'pair':workflow_improvement_gate(report), 'baseline':resources(next(run for run in report['runs'] if not run['enabled'])), 'jev':resources(next(run for run in report['runs'] if run['enabled']))} for report in reports})
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({key:audit[key] for key in ('passed','gains','regressions','reasons')}, ensure_ascii=False))
    if not audit['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
