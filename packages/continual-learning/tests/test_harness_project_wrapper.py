from __future__ import annotations

from support import run_bun


def test_parent_bound_template_covers_same_project_wrappers_only() -> None:
    # Given a parent-bound current project, when proposing a push-family matcher,
    # then retain actual wrapper coverage without matching printed/foreign calls.
    result = run_bun(r'''
      import { projectPushTemplate } from './packages/continual-learning/extensions/harness-command-coverage.ts';
      import { buildHarnessConsolidatorPrompt } from './packages/continual-learning/extensions/planner-prompts.ts';
      const template = projectPushTemplate('/work/mitt');
      if (!template) throw new Error('Missing bounded template');
      const re = new RegExp(template);
      for (const command of ['git push --dry-run', 'cd /work/mitt && git push --dry-run',
        "cd '/work/mitt' && git push origin topic", 'cd "/work/mitt" && git -C . push --dry-run',
        'cd . && git --no-pager push --dry-run']) {
        if (!re.test(command)) throw new Error('Missing current-project coverage');
      }
      for (const command of ['cd /work/other && git push --dry-run',
        'cd /work/mitt/../other && git push', "echo 'cd /work/mitt && git push'",
        "printf '%s' 'cd /work/mitt && git push'", 'echo x; cd /work/mitt && git push',
        'cd /work/mitt || git push', 'git\npush', 'git\u00a0push', 'git push\r']) {
        if (re.test(command)) throw new Error('Expanded scope or printed false match');
      }
      const prompt = buildHarnessConsolidatorPrompt({runId:'r', scopeDigest:'s', artifactHash:'h',
        snapshotPath:'/tmp/s', dossierPath:'', repoRoot:'/work/mitt'});
      if (!prompt.includes(template) || !prompt.includes('cd /work/mitt && git push --dry-run')) throw new Error('Planner omitted parent-bound coverage');
      if (projectPushTemplate('/work/a\nb') !== undefined || projectPushTemplate('/work/a$(pwd)') !== undefined
        || projectPushTemplate('relative') !== undefined) throw new Error('Unsupported shell spelling assumed');
      const dotted = new RegExp(projectPushTemplate('/work/a.b')!);
      if (dotted.test('cd /work/axb && git push')) throw new Error('Root not regex escaped');
      console.log(JSON.stringify('ok'));
    ''')
    assert result == 'ok'
