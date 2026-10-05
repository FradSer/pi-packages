"""The upstream glossary rename preserves references stored by earlier sessions."""
from matt_pocock_helpers import run_typescript


def test_previous_context_format_id_restores_the_new_glossary_reference() -> None:
    result = run_typescript('''
        import { resolveWorkflowContext, resolveAccessibleReference } from "./packages/matt-pocock/src/resolver.ts";
        const restored = resolveWorkflowContext("improve-codebase-architecture", ["domain-modeling", "CONTEXT-FORMAT"]);
        const oldReference = resolveAccessibleReference("domain-modeling", [], "CONTEXT-FORMAT");
        const newReference = resolveAccessibleReference("domain-modeling", [], "GLOSSARY-FORMAT");
        console.log(JSON.stringify({ restored, oldReference, newReference }));
    ''')
    assert result["oldReference"] == result["newReference"]
    assert "GLOSSARY-FORMAT" in result["restored"]["loaded"]
    assert 'source="procedure/GLOSSARY-FORMAT"' in result["restored"]["content"]
