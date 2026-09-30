"""The user Harness layer follows the project, like private Memory does.

Memory scopes private state per canonical project path, so a rule authored for
one project cannot silently govern another. The user layer is scoped the same
way — in a directory parallel to `memory/`, not inside it, because a Memory root
admits only regular `.md` children and a JSON configuration there fails
consolidation's privacy validation and aborts the run. That failure was hit for
real during development, which is why the placement is asserted rather than
assumed.
"""

from __future__ import annotations

from support import isolated_run_bun

SNIPPET = r"""
      import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
      const { configPaths, loadLayers } = await import('./packages/continual-learning/extensions/guardrail-config.ts');
      const { escapedProjectPath } = await import('./packages/continual-learning/extensions/memory-paths.ts');
      const agent = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'scoped-harness-')));
      const a = path.join(agent,'a'), b = path.join(agent,'b');
      fs.mkdirSync(path.join(a,'.pi'),{recursive:true});
      fs.mkdirSync(path.join(b,'.pi'),{recursive:true});
      const pathsA = configPaths(a, agent), pathsB = configPaths(b, agent);
      fs.mkdirSync(path.dirname(pathsA.userScoped),{recursive:true});
      fs.writeFileSync(pathsA.userScoped, JSON.stringify({rules:[{id:'only-a',bash:'^only-a',action:'block',message:'A only.'}]}));
      fs.writeFileSync(path.join(agent,'harness.json'), JSON.stringify({rules:[{id:'everywhere',bash:'^everywhere',action:'block',message:'Everywhere.'}]}));
      // A project layer too, so the precedence order is exercised rather than
      // asserted over a two-layer list.
      fs.writeFileSync(path.join(a,'.pi','harness.json'), JSON.stringify({rules:[{id:'shared-a',bash:'^shared-a',action:'block',message:'Shared.'}]}));
      const layersA = loadLayers(a, agent).map((l) => l.source);
      const layersB = loadLayers(b, agent).map((l) => l.source);
      const scopeA = escapedProjectPath(a);
      const memoryRoot = path.join(agent,'memory',scopeA);
      const { mergeLayers, evaluateBash } = await import('./packages/continual-learning/extensions/guardrail-engine.ts');
      const mergedA = mergeLayers(loadLayers(a, agent), []);
      const mergedB = mergeLayers(loadLayers(b, agent), []);
      console.log(JSON.stringify({
        layersA, layersB, scopeA,
        scopedRelative: path.relative(agent, pathsA.userScoped),
        insideMemoryRoot: pathsA.userScoped.startsWith(memoryRoot + path.sep),
        sameScopeKeyAsMemory: path.basename(pathsA.userScoped) === scopeA + '.json',
        distinctPerProject: pathsA.userScoped !== pathsB.userScoped,
        aBlocks: evaluateBash(mergedA, 'only-a build').decision,
        bBlocks: evaluateBash(mergedB, 'only-a build').decision,
        aSeesGlobal: evaluateBash(mergedA, 'everywhere').decision,
        bSeesGlobal: evaluateBash(mergedB, 'everywhere').decision,
      }));
"""


def test_the_user_layer_follows_the_project_like_private_memory() -> None:
    value = isolated_run_bun(SNIPPET)
    # Isolation: a personal rule for one project governs that project only.
    assert "user.scoped" in value["layersA"], value
    assert "user.scoped" not in value["layersB"], value
    assert value["aBlocks"] == "block", value
    assert value["bBlocks"] == "execute", value
    # The all-projects layer still governs both, so scoping added isolation
    # rather than removing a capability.
    assert value["aSeesGlobal"] == "block" and value["bSeesGlobal"] == "block", value
    assert value["distinctPerProject"] is True, value
    # The all-projects user layer is kept, so a cross-project rule still applies.
    assert "user" in value["layersA"] and "user" in value["layersB"], value
    # Nearest layer wins: this project's own file sits above the global one.
    assert value["layersA"].index("user.scoped") > value["layersA"].index("user"), value
    assert value["layersA"].index("project") > value["layersA"].index("user.scoped"), value


def test_the_scoped_layer_reuses_the_memory_scope_key_and_stays_out_of_a_memory_root() -> None:
    value = isolated_run_bun(SNIPPET)
    assert value["sameScopeKeyAsMemory"] is True, value
    # A Memory root admits only regular `.md` children; a JSON configuration
    # beside them fails privacy validation and aborts consolidation outright.
    assert value["insideMemoryRoot"] is False, value
    assert value["scopedRelative"].startswith("harness/"), value
