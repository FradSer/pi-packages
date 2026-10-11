"""Read-only result analysis. No model, Docker, or hidden feedback to agents."""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parent / 'runs/controlled-20261010'


def phase_cost(phase: dict) -> float:
    return phase.get('costEstimatedUsd', 0) + phase.get('jevEstimatedUsd', 0) + (
        phase_cost(phase['handoff']) if phase.get('handoff') else 0)


def phase_requests(phase: dict) -> int:
    return phase.get('requests', 0) + (phase_requests(phase['handoff']) if phase.get('handoff') else 0)


def phase_finished(phase: dict) -> bool:
    return phase.get('reportCompleted', False) or (phase_finished(phase['handoff']) if phase.get('handoff') else False)


def exact_p(wins: int, losses: int) -> float:
    n = wins + losses
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / (2**n)) if n else 1.0


def main() -> None:
    rows = json.loads((ROOT / 'results.json').read_text())
    spend = json.loads((ROOT / 'spend.json').read_text())
    mechanism = json.loads((ROOT / 'mechanism/receipt.json').read_text())
    assert len(rows) == 4
    assert all(set(r['arms']) == {'baseline', 'e2e'} for r in rows)
    stats = {arm: {'passed': 0, 'scored': 0, 'rescued': 0, 'regressed': 0, 'reportsCompleted': 0,
                   'reviewFixEstimatedUsd': 0.0, 'allocatedFullEstimatedUsd': 0.0,
                   'requests': 0, 'freshNativeReviews': 0, 'validNativeArguments': 0}
             for arm in ['baseline', 'e2e']}
    lines = ['# E2E 四题同初稿配对诊断实验', '',
             '这是人工编写的合成小项目研究，单独检验 review 方式；不冒充 ProMax 或生产项目收益。', '',
             '| 任务 | 初稿独立评分 | 模型 review→fix | E2E review→fix |', '| --- | --- | --- | --- |']
    def score(g):
        if g['passed'] is None:
            return '未评分（' + g['status'] + '）'
        return ('通过' if g['passed'] else '失败') + f"（{g.get('passCount','?')}/{g.get('total','?')}）"
    wins = losses = 0
    for row in rows:
        a, b = row['arms']['baseline']['final'], row['arms']['e2e']['final']
        lines.append(f"| {row['task']} | {score(row['initial'])} | {score(a)} | {score(b)} |")
        if isinstance(a['passed'], bool) and isinstance(b['passed'], bool):
            wins += b['passed'] and not a['passed']
            losses += a['passed'] and not b['passed']
        for arm, data in row['arms'].items():
            s = stats[arm]
            assert data['sameInitialSha256'] == row['initial']['sourceSha256']
            assert data['review']['sourceBefore'] == row['initial']['sourceSha256']
            assert data['review']['sourceAfter'] == row['initial']['sourceSha256']
            assert data['fix']['sourceAfter'] == data['final']['sourceSha256']
            assert data['review']['fixedInputsIntact'] and data['fix']['fixedInputsIntact']
            g = data['final']
            s['passed'] += g['passed'] is True
            s['scored'] += isinstance(g['passed'], bool)
            s['rescued'] += row['initial']['passed'] is False and g['passed'] is True
            s['regressed'] += row['initial']['passed'] is True and g['passed'] is False
            s['reportsCompleted'] += phase_finished(data['review']) and phase_finished(data['fix'])
            increment = phase_cost(data['review']) + phase_cost(data['fix'])
            s['reviewFixEstimatedUsd'] += increment
            s['allocatedFullEstimatedUsd'] += increment + phase_cost(row['execute']) / 2
            s['requests'] += phase_requests(data['review']) + phase_requests(data['fix'])
            if arm == 'e2e':
                packet = json.loads((ROOT / 'results' / row['task'] / arm / 'review-packet.json').read_text())
                s['freshNativeReviews'] += any(x.get('details', {}).get('verifiedRun') is True for x in packet['results'])
                s['validNativeArguments'] += data['review'].get('nativeArgumentsValid', False)
    summary = {'initialPassed': sum(r['initial']['passed'] is True for r in rows), 'pairs': 4,
               'e2eOnlyWins': wins, 'baselineOnlyWins': losses, 'pairedExactTwoSidedP': exact_p(wins, losses),
               'arms': stats, 'spend': spend, 'billingVerified': False}
    (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2))
    lines += ['', '| 工作流 | 最终严格通过/已评分 | 救回 | 回归 | 完整 review/fix 报告 | review+fix 费用估算 | 含分摊初稿费用 |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for arm, s in stats.items():
        lines.append(f"| {arm} | {s['passed']}/{s['scored']} | {s['rescued']} | {s['regressed']} | {s['reportsCompleted']}/4 | ${s['reviewFixEstimatedUsd']:.6f} | ${s['allocatedFullEstimatedUsd']:.6f} |")
    lines += ['', f"初稿严格通过 {summary['initialPassed']}/4；E2E 单独胜出 {wins} 题，对照单独胜出 {losses} 题。配对精确双侧 p={exact_p(wins, losses):.3f}，四题不足以支持普遍收益或等效性。",
              f"原生新鲜验证覆盖 {stats['e2e']['freshNativeReviews']}/4 组；实际参数符合冻结要求 {stats['e2e']['validNativeArguments']}/4 组。真实机制预检使用 {mechanism['requests']} 次请求，其中 Jev {mechanism['jevRequests']} 次。",
              f"本轮共转发 {spend['requests']} 次请求（含预检、Jev及失败请求）。含历史预留的保守累计预算占用 ${spend['reservedCumulativeUsd']:.2f}，上限 $19；这不是账单金额。", '',
              '## 解释边界', '',
              '- 两组从相同真实模型初稿分叉，公开检查相同；差异是 review 方式。不能据此推断加载插件后的完整执行流程收益。',
              '- 全部初稿正确时没有二元正确率改善空间；增加测试、完成报告、fresh proof 均不能算作修复收益。',
              '- 评分为冻结公开+隐藏断言，模型不能访问隐藏断言或参考实现；测试覆盖有限，不能证明无缺陷。',
              '- 项目、参考实现、公开检查由 Codex 编写，其人工成本未定价。它们不是随机生产任务；模型及任务外推有限。',
              '- 费用来自 Pi 配置用量估算；中断请求按请求预算保守预留，实际账单未验证。历史已知去重估算约 $2.974，另有未知中断用量。',
              '- Jev价格来源：[官方模型页](https://docs.typesafe.ai/models)。实验按输入 $0.042/M、输出免费估算，保留实际模型名与用量。',
              '- 所有原始事件、请求数、源码快照、独立评分和协议哈希保留；无结果驱动换题或付费重跑。', '']
    (ROOT / 'REPORT.zh-CN.md').write_text('\n'.join(lines))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
