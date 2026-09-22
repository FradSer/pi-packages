from support import PKG_DIR as PKG, isolated_run_bun as run_bun


def test_postgeneration_compatibility_is_registered_without_new_authoring_selectors() -> None:
    source = (PKG/'index.ts').read_text()
    assert 'registerOutputChecks(pi)' in source
    assert (PKG/'extensions/output-checks.ts').exists()
    result = run_bun('''
      import * as engine from './packages/continual-learning/extensions/guardrail-engine.ts';
      const invalid=['output','artifact','tool-call'].map(phase=>engine.validateRuleDeclaration({id:'unsupported',phase,tools:['write'],paths:['content'],pattern:'x',reason:'old'}));
      console.log(JSON.stringify({exports:Object.keys(engine),invalid}));
    ''')
    assert all(result['invalid'])
    assert all(name not in result['exports'] for name in ['evaluate','evaluatePhase','validatePolicyDeclaration','validateSkillPromptDeclaration','DEFAULT_POLICIES'])
