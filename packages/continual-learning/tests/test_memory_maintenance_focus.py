from pathlib import Path


PROMPT = Path(__file__).resolve().parents[1] / 'prompts/incremental-memory-consolidator.md'


def test_maintenance_prompt_requires_claim_focused_corrections_and_full_context() -> None:
    text = PROMPT.read_text()
    assert 'Organization is not wholesale summarization' in text
    assert 'Identify the particular obsolete, contradicted or misleading claim' in text
    assert 'Preserve unrelated established knowledge and its material conditions' in text
    assert 'Do not shorten or remove source conditions to reduce review cost' in text
    assert 'All original task evidence remains subject to complete review' in text
