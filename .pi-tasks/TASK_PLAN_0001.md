---
id: TASK_PLAN_0001
state: completed
phase: done
created_at: 2026-08-11T16:52:57.064Z
updated_at: 2026-08-12T02:11:33.954Z
title: 创建包，叫做 teammate ， skills 叫做 using-teammate 这样知识型的
---

## task prompt

创建包，叫做 teammate ， skills 叫做 using-teammate 这样知识型的

## decisions

Q1: What does the using-teammate knowledge skill document? The entire SKILL.md body depends on which "Teammate" this refers to — a knowledge skill can't be written until its subject is named, and the repo convention (reference-style prose, no scripts) is already pinned down by "知识型的".
A1: OpenAI's Teammate agents product — distill its public docs into a reference-style SKILL.md following the mattpocock knowledge-skill convention
Q2: SKILL.md 正文用什么语言写？ 仓库里所有既有 skill 正文都是英文（mattpocock、utils、memory、lark 的 SKILL.md），但你的请求用中文提出，且 README 是英中双语 —— 这个选择决定整个正文的每一行。
A2: 英文 —— 与仓库全部 skill 正文惯例一致，且 OpenAI 官方文档本身是英文，术语和引用链接无需翻译
Q3: Should using-teammate be model-invoked or user-invoked? This decides the frontmatter and every word of the description — the mattpocock convention splits skills on exactly this axis (model-invoked keeps trigger-phrase descriptions and pays context load; user-invoked sets disable-model-invocation: true so only /skill:using-teammate fires it).
A3: model-invoked — write a rich trigger-phrase description so the agent auto-loads the skill whenever the user asks to build, configure, or use an OpenAI Teammate, matching the consolidate pattern in this repo
Q4: Which Teammate surface should using-teammate document — the ChatGPT workspace feature, the developer API, or both? OpenAI's "Teammates" spans two doc sets (workspace-UI guides vs the developer API with workflow-as-code, knowledge files, and endpoints), and the choice sets every section header and roughly doubles the body if both are covered.
A4: make the developer API the core — workflow.md-as-code, knowledge files, endpoints, thread attachment — plus a short ChatGPT-UI usage section, since the trigger phrases cover build/configure/use
Q5: How concrete and how verified should the using-teammate body be — full embedded API details (endpoint paths, workflow.md format, knowledge-file params, thread-attachment JSON) fetched from OpenAI's live docs, or a durable conceptual distillation that links out to developer.openai.com? This decides whether the model-invoked agent can build a teammate directly from the SKILL.md or must fetch docs at call time, and how much beta-API drift the skill absorbs.
A5: embed concrete, live-verified details — fetch the OpenAI Teammates docs (developer.openai.com Teammates guide, API reference, and knowledge pages) during this build and distill exact endpoint paths, request/response JSON, workflow.md syntax, and knowledge-file formats into the SKILL.md, with inline links to each source page.

## handoff

handoff_at: 2026-08-12T02:11:33.952Z
decisions: 5
