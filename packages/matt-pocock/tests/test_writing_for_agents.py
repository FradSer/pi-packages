from test_package import run_typescript


def test_writing_capability_includes_model_aware_authoring_guidance() -> None:
    result = run_typescript("""
        import { resolveProcedureBundle } from "./packages/matt-pocock/src/resolver.ts";
        console.log(JSON.stringify(resolveProcedureBundle("writing-for-agents")));
    """)
    text = result["content"]
    for guidance in (
        "Rethinking skills and prompts for GPT-6 Astra",
        "adding or changing a migration, or reviewing its rollout",
        "minimal router",
        "architecture.md for service boundaries",
        "models used by contributors",
        "disposable fixtures and have no production access",
        "production writes, destructive operations, and external publication",
        "running it, inspecting the result, fixing failures",
        "exploration scope and stopping condition",
    ):
        assert guidance in text, f"Missing authoring guidance: {guidance}"
