"""Conservative Python test-preservation adapter helper; no semantic equivalence claim.

Compare trusted original source with candidate source. A frozen protocol can allow
specific migrations before execution; never infer an allowance from candidate text.
This guard does not replace independent review of fixtures, helpers or control flow.
"""
from __future__ import annotations
import ast
from collections import Counter
from typing import Any


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _name(node.value) + '.' + node.attr
    return ''


def _functions(tree: ast.AST, prefix: str = '') -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in getattr(tree, 'body', []):
        if isinstance(node, ast.ClassDef):
            result.update(_functions(node, prefix + node.name + '.'))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test'):
            result[prefix + node.name] = node
    return result


def _checks(function: ast.AST) -> list[ast.AST]:
    checks: list[ast.AST] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assert):
            checks.append(node)
        elif isinstance(node, ast.Call):
            name = _name(node.func)
            if name.endswith('.raises') or name.endswith('.fail') or '.testing.assert' in name or name.startswith('self.assert'):
                checks.append(node)
    return checks


def compare_sources(original: str, candidate: str, path: str) -> dict[str, Any]:
    """Require each original test and assertion/error expectation to remain intact."""
    findings: list[dict[str, Any]] = []
    try:
        original_tree, candidate_tree = ast.parse(original), ast.parse(candidate)
        before, after = _functions(original_tree), _functions(candidate_tree)
    except SyntaxError as error:
        return {'passed': False, 'findings': [{'path': path, 'location': f'{path}:{error.lineno}', 'kind': 'invalid_test_source', 'expected': 'valid Python', 'observed': error.msg}]}
    for name, function in before.items():
        current = after.get(name)
        if current is None:
            findings.append({'path': path, 'location': f'{path}:{function.lineno}', 'kind': 'test_removed', 'test': name, 'expected': name, 'observed': 'missing'})
            continue
        available = Counter(ast.dump(node, include_attributes=False) for node in _checks(current))
        for node in _checks(function):
            key = ast.dump(node, include_attributes=False)
            if available[key]:
                available[key] -= 1
            else:
                findings.append({'path': path, 'location': f'{path}:{node.lineno}', 'kind': 'assertion_removed_or_changed', 'test': name, 'expected': ast.unparse(node)[:2048], 'observed': ast.get_source_segment(candidate, current)[:2048]})
    def disabling_nodes(tree: ast.AST, scope: str = '') -> list[tuple[str, ast.AST]]:
        if isinstance(tree, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope += '.' + tree.name
        result: list[tuple[str, ast.AST]] = []
        target = tree.func if isinstance(tree, ast.Call) else tree
        if isinstance(tree, (ast.Call, ast.Attribute)) and _name(target).split('.')[-1] in {'skip', 'skipif', 'xfail'}:
            result.append((scope, tree))
        for child in ast.iter_child_nodes(tree):
            result.extend(disabling_nodes(child, scope))
        return result
    allowed = Counter((scope, ast.dump(node, include_attributes=False)) for scope, node in disabling_nodes(original_tree))
    for scope, node in disabling_nodes(candidate_tree):
        key = (scope, ast.dump(node, include_attributes=False))
        if allowed[key]:
            allowed[key] -= 1
        else:
            findings.append({'path': path, 'location': f'{path}:{node.lineno}', 'kind': 'new_skip_or_xfail', 'test': scope, 'expected': 'no new test-disabling marker or call in this scope', 'observed': ast.unparse(node)[:2048]})
    return {'passed': not findings, 'originalTests': len(before), 'findings': findings}
