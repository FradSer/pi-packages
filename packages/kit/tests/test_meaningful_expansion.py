"""Shared rendering contract: an expansion hint must reveal display content."""

from __future__ import annotations

import pytest

from test_pi_kit import run_typescript


@pytest.fixture(scope="module")
def rendered_cases() -> dict[str, object]:
    return run_typescript(r"""
        import {
          bindLifecycleRenderers, createToolLifecycleResultRenderer, createStaticToolLifecycleResultRenderer,
          createToolLifecycleMessageRenderer, createStaticToolLifecycleMessageRenderer,
          eventToolLifecycle, renderToolLifecycle,
        } from './packages/kit/src/index.ts';
        import { truncateToWidth, visibleWidth, wrapTextWithAnsi } from '@earendil-works/pi-tui';
        import { stripVTControlCharacters } from 'node:util';
        const theme = { fg: (_, text) => text, bg: (_, text) => text, bold: text => text };
        const geometry = { fit: truncateToWidth, visibleWidth, wrapDetail: wrapTextWithAnsi, expandHint: 'ctrl+o to expand' };
        const raw = { content: 'MODEL-ONLY-BODY', details: { internal: 'state', action: 'complete' } };
        const builders = {
          result: createToolLifecycleResultRenderer,
          staticResult: createStaticToolLifecycleResultRenderer,
          message: createToolLifecycleMessageRenderer,
          staticMessage: createStaticToolLifecycleMessageRenderer,
          boundResult: options => bindLifecycleRenderers(options).result(options.createSpec),
          boundMessage: options => bindLifecycleRenderers(options).message(options.createSpec),
        };
        const specs = {
          empty: eventToolLifecycle('probe', 'done'),
          whitespace: eventToolLifecycle('probe', 'done', { details: [' ', '\t', '\x1b[31m\x1b[0m', '\n'] }),
          body: eventToolLifecycle('probe', 'done', { details: ['first', '', 'second', 'first'] }),
          long: eventToolLifecycle('probe', '检查 café evidence '.repeat(9).trim()),
          multiline: eventToolLifecycle('probe', 'first\n\nsecond'),
          carriage: eventToolLifecycle('probe', 'first\rsecond', { summary: ['Answer: one\rtwo'] }),
          trailing: eventToolLifecycle('probe', 'done' + ' '.repeat(100), { summary: ['Answer: yes' + ' '.repeat(100)] }),
          trailingPreview: eventToolLifecycle('probe', 'done', { expandedSubject: 'done   ' }),
          trailingBreak: eventToolLifecycle('probe', 'done\r\n\r\n', { summary: ['Answer: yes\r\n\r\n'] }),
          summary: eventToolLifecycle('probe', 'decision', { summary: ['Answer: ' + '检查 café '.repeat(12).trim(), 'line one\n\nline two'] }),
          shortSummary: eventToolLifecycle('probe', 'decision', { summary: ['Answer: yes'] }),
          blankSummary: eventToolLifecycle('probe', 'done', { summary: [' \n ', '\t'] }),
          explicit: eventToolLifecycle('probe', 'preview', { expandedSubject: 'full\n\n' + 'evidence '.repeat(35).trim() }),
          limited: eventToolLifecycle('probe', 'done', { details: ['hidden'], detailLimit: 0 }),
          readback: eventToolLifecycle('probe', 'report', { details: Array.from({ length: 65 }, (_, i) => `finding ${i}`), detailLimit: 'all' }),
        };
        const rows = {};
        for (const [name, build] of Object.entries(builders)) {
          rows[name] = {};
          for (const [key, spec] of Object.entries(specs)) {
            const render = build({ ...geometry, createSpec: () => spec });
            const output = {};
            for (const width of [1, 2, 8, 48, 90, 240]) {
              output[width] = {};
              for (const expanded of [false, true]) {
                const rendered = render(raw, { expanded }, theme, {}).render(width);
                output[width][expanded ? 'expanded' : 'collapsed'] = rendered.slice(1, -1)
                  .map(line => stripVTControlCharacters(line).slice(width > 2 ? 1 : 0).trimEnd());
                output[width][expanded ? 'expandedBounded' : 'collapsedBounded'] = rendered.every(line => visibleWidth(line) <= width && !/[\r\n]/.test(line));
              }
            }
            const withoutMetadata = render({ content: '' }, { expanded: false }, theme, {}).render(90);
            rows[name][key] = { widths: output, withoutMetadata: withoutMetadata.slice(1, -1).map(line => stripVTControlCharacters(line).slice(1).trimEnd()) };
          }
        }
        const expected = {};
        for (const width of [48, 90, 240]) {
          expected[width] = {};
          for (const [key, spec] of Object.entries(specs)) {
            expected[width][key] = [
              ...wrapTextWithAnsi(`[probe] ${spec.expandedSubject ?? spec.subject}`, width - 2),
              ...(spec.summary ?? []).flatMap(line => wrapTextWithAnsi(line, width - 2)),
            ].map(line => line.trimEnd());
          }
        }
        const noWrapperCarriage = [false, true].map(expanded => renderToolLifecycle(specs.carriage, {
          ...geometry, wrapDetail: undefined, theme, width: 90, expanded,
        }).slice(1, -1).map(line => stripVTControlCharacters(line).trimEnd().slice(1)));
        const noWrapperTrailing = renderToolLifecycle(specs.trailingBreak, {
          ...geometry, wrapDetail: undefined, theme, width: 90,
        }).slice(1, -1).map(line => stripVTControlCharacters(line).trimEnd().slice(1));
        const direct = (expandable, spec = specs.empty) => renderToolLifecycle(spec, { ...geometry, theme, width: 90, expandable })
          .slice(1, -1).map(line => stripVTControlCharacters(line).trim());
        const errors = {};
        for (const [name, build] of Object.entries(builders).filter(([name]) => name.toLowerCase().includes('result'))) {
          const render = build({ ...geometry, createSpec: () => specs.empty });
          errors[name] = render({ content: 'failure reason\nadditional evidence' }, { expanded: true }, theme, { isError: true })
            .render(90).map(line => stripVTControlCharacters(line).trim()).filter(Boolean);
        }
        console.log(JSON.stringify({ rows, expected, errors, noWrapperCarriage, noWrapperTrailing, directTrue: direct(true), directFalse: direct(false, specs.body) }));
    """)


@pytest.mark.parametrize("factory", ["result", "staticResult", "message", "staticMessage", "boundResult", "boundMessage"])
def test_all_factories_ignore_opaque_metadata_and_blank_details(rendered_cases: dict[str, object], factory: str) -> None:
    cases = rendered_cases["rows"][factory]
    for name in ("empty", "whitespace", "limited", "trailingPreview"):
        case = cases[name]
        assert case["widths"]["90"]["collapsed"] == ["[probe] done"]
        assert case["widths"]["90"]["expanded"] == ["[probe] done"]
        assert case["withoutMetadata"] == case["widths"]["90"]["collapsed"]
    assert cases["shortSummary"]["widths"]["90"]["collapsed"] == ["[probe] decision", "Answer: yes"]
    assert "ctrl+o" not in "\n".join(cases["blankSummary"]["widths"]["90"]["collapsed"])


@pytest.mark.parametrize("factory", ["result", "staticResult", "message", "staticMessage", "boundResult", "boundMessage"])
def test_default_long_titles_and_summaries_reveal_full_native_wrapped_text(rendered_cases: dict[str, object], factory: str) -> None:
    cases = rendered_cases["rows"][factory]
    for key in ("long", "multiline", "carriage", "summary", "explicit"):
        for width in ("48", "90", "240"):
            rendered = cases[key]["widths"][width]
            assert rendered["expanded"] == rendered_cases["expected"][width][key]
            assert "MODEL-ONLY" not in "\n".join(rendered["expanded"])
            if key != "long" or width != "240":
                assert "ctrl+o to expand" in "\n".join(rendered["collapsed"])
        assert all(value["expandedBounded"] and value["collapsedBounded"] for value in cases[key]["widths"].values())
    # Resizing reveals the entire title, so expansion has nothing left to offer.
    assert "ctrl+o" not in "\n".join(cases["long"]["widths"]["240"]["collapsed"])


def test_trailing_spaces_do_not_offer_empty_expansion(rendered_cases: dict[str, object]) -> None:
    for cases in rendered_cases["rows"].values():
        for width in ("48", "90", "240"):
            view = cases["trailing"]["widths"][width]
            assert view["collapsed"] == ["[probe] done", "Answer: yes"]
            assert view["expanded"] == view["collapsed"]
            trailing_break = cases["trailingBreak"]["widths"][width]
            assert trailing_break["collapsed"] == ["[probe] done", "Answer: yes"]
            assert [line for line in trailing_break["expanded"] if line] == trailing_break["collapsed"]
    assert rendered_cases["noWrapperTrailing"] == ["[probe] done", "Answer: yes"]


def test_bare_carriage_returns_are_line_breaks_without_native_wrapper(rendered_cases: dict[str, object]) -> None:
    collapsed, expanded = rendered_cases["noWrapperCarriage"]
    assert collapsed == ["[probe] first second · ctrl+o to expand", "Answer: one two"]
    assert expanded == ["[probe] first", "second", "Answer: one", "two"]


def test_shared_renderer_preserves_paragraphs_repeated_values_and_unbounded_readbacks(rendered_cases: dict[str, object]) -> None:
    for cases in rendered_cases["rows"].values():
        assert cases["body"]["widths"]["90"]["expanded"] == ["[probe] done", "first", "", "second", "first"]
        assert cases["readback"]["widths"]["90"]["expanded"] == ["[probe] report", *[f"finding {i}" for i in range(65)]]
        assert "ctrl+o to expand" in cases["body"]["widths"]["90"]["collapsed"][0]


def test_legacy_low_level_override_and_error_evidence_remain_supported(rendered_cases: dict[str, object]) -> None:
    assert rendered_cases["directTrue"] == ["[probe] done · ctrl+o to expand"]
    assert rendered_cases["directFalse"] == ["[probe] done"]
    for rows in rendered_cases["errors"].values():
        assert rows == ["[probe] failed · failure reason", "additional evidence"]
