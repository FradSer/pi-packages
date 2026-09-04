---
name: recap-inline-code-markers
description: recap cleanup preserves paired inline-code backticks at the start of summaries
type: project
---

## Why

Removing leading and trailing backticks independently can delete only the opening marker from a summary that begins with inline code, leaving malformed Markdown.

## How to apply

In packages/recap/extensions/recap.ts, remove quote characters only when a recognized opening and closing pair wraps the complete summary. Preserve balanced inline backticks when code appears at the start of a longer recap. Keep regression coverage in the recap feature and package test.