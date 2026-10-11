from __future__ import annotations

import json
from pathlib import Path

from support import run_bun


def run_menu(source: str, root: Path) -> dict:
    return run_bun(
        source,
        {"MEMORY_MENU_TEST_ROOT": str(root)},
    )


def test_memory_menu_has_three_first_level_actions_and_safe_browse(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import fs from 'node:fs'; import path from 'node:path';
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const privateRoot = path.join(process.env.MEMORY_MENU_TEST_ROOT, 'private');
          fs.mkdirSync(privateRoot, { recursive: true });
          const privateIndex = path.join(privateRoot, 'MEMORY.md');
          fs.writeFileSync(privateIndex, '- [preference.md](preference.md) (harness only)\n- [fact.md](fact.md)\n');
          const selections = ['Browse memories', 'Private · preference.md · Keep changes small', 'Close'];
          const menus = []; const notices = [];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return selections.shift(); },
            notify: (message, type) => notices.push({ message, type }),
          }};
          const writes = [];
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 2 }),
            loadMemories: async () => ({ entries: [
              { filename: 'preference.md', source: 'harness', readPath: '/private/preference.md', content: 'Keep changes small', description: 'Keep changes small' },
              // Canonical/private root ownership does not imply private data.
              { filename: 'fact.md', source: 'harness', readPath: '/private/fact.md', content: 'Project fact', description: 'Project fact' },
            ], totalEntries: 2, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0,
              indexes: [{ source: 'harness', readPath: privateIndex, rootPath: privateRoot, available: true }], maxTotalChars: 6000 }),
            listHistory: async () => [],
            manage: async () => true,
            selectModel: async () => { writes.push('model'); },
            toggleAutoMemory: async () => { writes.push('toggle'); },
            isBusy: () => false,
          });
          console.log(JSON.stringify({ menus, notices, writes }));
        ''',
        tmp_path,
    )
    assert len(result["menus"]) == 5
    assert result["menus"][0]["options"] == ["Browse memories", "Learning settings", "Recent learning", "Close"]
    assert "auto on" in result["menus"][0]["title"]
    assert "provider/model" in result["menus"][0]["title"]
    assert "2 entries" in result["menus"][0]["title"]
    assert result["menus"][1]["options"] == ["Private · preference.md · Keep changes small", "Shared · fact.md · Project fact", "Back"]
    assert result["writes"] == []


def test_memory_menu_settings_and_advanced_policy_delegate_without_writes(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const choices = ['Learning settings', 'Advanced phase policies', 'Harness policy', 'propose — save for review'];
          const menus = []; const delegated = []; const writes = [];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); },
            notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 0 }),
            loadMemories: async () => ({ entries: [], totalEntries: 0, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0, indexes: [], maxTotalChars: 6000 }),
            listHistory: async () => [],
            manage: async (command) => { delegated.push(command); return true; },
            selectModel: async () => { writes.push('model'); },
            toggleAutoMemory: async () => { writes.push('toggle'); },
            isBusy: () => false,
          });
          console.log(JSON.stringify({ menus, delegated, writes }));
        ''',
        tmp_path,
    )
    assert result["menus"][1]["options"] == ["Select learning model", "Toggle automatic learning", "Advanced phase policies"]
    assert result["menus"][2]["options"] == ["Memory policy", "Harness policy", "Agents policy"]
    assert result["menus"][3]["options"] == ["apply — save validated changes", "propose — save for review", "off — skip automatic phase"]
    assert result["delegated"] == ["policy harness propose"]
    assert result["writes"] == []


def test_memory_menu_recent_learning_does_not_offer_undo_for_proposals(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const choices = ['Recent learning', '#1 saved proposal · proposed · 10-03 00:00 · memory'];
          const menus = []; const delegated = [];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); },
            notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: false, model: 'provider/model', entries: 0 }),
            loadMemories: async () => ({ entries: [], totalEntries: 0, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0, indexes: [], maxTotalChars: 6000 }),
            listHistory: async () => [
              { id: 'proposal-1', phase: 'memory', status: 'proposed', createdAt: '2026-10-03T00:00:00Z', changes: [], proposal: { operations: [] } },
              { id: 'applied-1', phase: 'harness', status: 'applied', createdAt: '2026-10-02T00:00:00Z', changes: [], proposal: undefined },
            ],
            manage: async (command) => { delegated.push(command); return true; },
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ menus, delegated }));
        ''',
        tmp_path,
    )
    assert result["menus"][1]["options"] == ["#1 saved proposal · proposed · 10-03 00:00 · memory", "#2 saved proposal · applied · 10-02 00:00 · harness", "Back"]
    assert result["menus"][2]["options"] == ["Close"]
    assert result["delegated"] == []


def test_memory_menu_sanitizes_external_model_in_title(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const menus = []; const choices = ['Learning settings', undefined];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); },
            notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/' + String.fromCharCode(27) + '[31munsafe' + String.fromCharCode(7), entries: 0 }),
            loadMemories: async () => ({ entries: [], totalEntries: 0, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0, indexes: [], maxTotalChars: 6000 }),
            listHistory: async () => [], manage: async () => true,
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ titles: menus.map(menu => menu.title) }));
        ''',
        tmp_path,
    )
    assert len(result["titles"]) == 3
    for title in result["titles"]:
        assert "\x1b" not in title
        assert "\x07" not in title
        assert "unsafe" in title


def test_memory_menu_does_not_call_an_unreadable_canonical_entry_shared(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const choices = ['Browse memories', 'Canonical · maybe-private.md · Unknown provenance', 'Close'];
          const menus = [];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); },
            notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 1 }),
            loadMemories: async () => ({ entries: [
              { filename: 'maybe-private.md', source: 'harness', readPath: '/private/maybe-private.md', content: 'Unknown provenance', description: 'Unknown provenance' },
            ], totalEntries: 1, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0,
              // The index claims to be available, but the bounded read fails.
              indexes: [{ source: 'harness', readPath: '/missing/MEMORY.md', rootPath: '/missing', available: true }], maxTotalChars: 6000 }),
            listHistory: async () => [], manage: async () => true,
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ options: menus[1].options }));
        ''',
        tmp_path,
    )
    assert result["options"][-1] == "Back"
    assert result["options"][:-1] == ["Canonical · maybe-private.md · Unknown provenance"]


def test_memory_menu_matches_parent_index_syntax_and_marks_unindexed_as_canonical(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import fs from 'node:fs'; import path from 'node:path';
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const root = path.join(process.env.MEMORY_MENU_TEST_ROOT, 'canonical'); fs.mkdirSync(root, { recursive: true });
          const index = path.join(root, 'MEMORY.md');
          fs.writeFileSync(index, [
            '- preference.md (harness only)',
            '- [Safe display label](safe.md) trailing annotation',
            '- [Private display label](private.md) (harness only) trailing annotation',
          ].join('\n') + '\n');
          const menus = []; const choices = ['Browse memories', null];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); }, notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 4 }),
            loadMemories: async () => ({ entries: [
              { filename: 'preference.md', source: 'harness', readPath: '/canonical/preference.md', content: 'preference', description: 'preference' },
              { filename: 'safe.md', source: 'harness', readPath: '/canonical/safe.md', content: 'safe', description: 'safe' },
              { filename: 'private.md', source: 'harness', readPath: '/canonical/private.md', content: 'private', description: 'private' },
              { filename: 'unindexed.md', source: 'harness', readPath: '/canonical/unindexed.md', content: 'unknown', description: 'unknown' },
            ], totalEntries: 4, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0,
              indexes: [{ source: 'harness', readPath: index, rootPath: root, available: true }], maxTotalChars: 6000 }),
            listHistory: async () => [], manage: async () => true,
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ options: menus[1].options }));
        ''',
        tmp_path,
    )
    assert result["options"][-1] == "Back"
    assert result["options"][:-1] == [
        "Private · preference.md · preference",
        "Shared · safe.md · safe",
        "Private · private.md · private",
        "Canonical · unindexed.md · unknown",
    ]


def test_memory_menu_prioritizes_link_target_and_ignores_prose_filename(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import fs from 'node:fs'; import path from 'node:path';
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const root = path.join(process.env.MEMORY_MENU_TEST_ROOT, 'grammar'); fs.mkdirSync(root, { recursive: true });
          const index = path.join(root, 'MEMORY.md');
          fs.writeFileSync(index, [
            '- decoy.md [Arbitrary display](private.md) (harness only)',
            '- prose description mentions prose.md',
          ].join('\n') + '\n');
          const menus = []; const choices = ['Browse memories', null];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); }, notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 3 }),
            loadMemories: async () => ({ entries: [
              { filename: 'decoy.md', source: 'harness', readPath: '/grammar/decoy.md', content: 'decoy', description: 'decoy' },
              { filename: 'private.md', source: 'harness', readPath: '/grammar/private.md', content: 'private', description: 'private' },
              { filename: 'prose.md', source: 'harness', readPath: '/grammar/prose.md', content: 'prose', description: 'prose' },
            ], totalEntries: 3, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0,
              indexes: [{ source: 'harness', readPath: index, rootPath: root, available: true }], maxTotalChars: 6000 }),
            listHistory: async () => [], manage: async () => true,
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ options: menus[1].options }));
        ''',
        tmp_path,
    )
    assert result["options"][-1] == "Back"
    assert result["options"][:-1] == [
        "Canonical · decoy.md · decoy",
        "Private · private.md · private",
        "Canonical · prose.md · prose",
    ]


def test_memory_menu_duplicate_index_records_are_canonical_not_shared(tmp_path: Path) -> None:
    result = run_menu(
        r'''
          import fs from 'node:fs'; import path from 'node:path';
          import { openMemoryMenu } from './packages/continual-learning/extensions/memory-menu.ts';
          const root = path.join(process.env.MEMORY_MENU_TEST_ROOT, 'duplicate'); fs.mkdirSync(root, { recursive: true });
          const index = path.join(root, 'MEMORY.md');
          fs.writeFileSync(index, '- duplicate.md\n- [Duplicate](duplicate.md) (harness only)\n');
          const menus = []; const choices = ['Browse memories', null];
          const ctx = { cwd: process.env.MEMORY_MENU_TEST_ROOT, hasUI: true, ui: {
            select: async (title, options) => { menus.push({ title, options }); return choices.shift(); }, notify: () => {},
          }};
          await openMemoryMenu(ctx, {
            status: async () => ({ autoMemory: true, model: 'provider/model', entries: 1 }),
            loadMemories: async () => ({ entries: [
              { filename: 'duplicate.md', source: 'harness', readPath: '/duplicate/duplicate.md', content: 'unknown', description: 'unknown' },
            ], totalEntries: 1, omittedEntries: 0, limitedEntries: 0, unavailableEntries: 0,
              indexes: [{ source: 'harness', readPath: index, rootPath: root, available: true }], maxTotalChars: 6000 }),
            listHistory: async () => [], manage: async () => true,
            selectModel: async () => {}, toggleAutoMemory: async () => {}, isBusy: () => false,
          });
          console.log(JSON.stringify({ options: menus[1].options }));
        ''',
        tmp_path,
    )
    assert result["options"][-1] == "Back"
    assert result["options"][:-1] == ["Canonical · duplicate.md · unknown"]
