# Teammate Pi Package

Reference skill for OpenAI Teammates — the developer API surface for AI teammates in ChatGPT: workspace agents, the Workspace Agents API, knowledge files via the Files API, file search and vector stores, and thread attachment.

**Version**: 0.1.0
**Display Name**: Teammate

## What This Package Does

Provides one model-invoked knowledge skill, `using-teammate`, a prose-only reference for building, creating, configuring, setting up, and using an OpenAI Teammate. It covers the documented developer surface: workflow configuration and workspace agents, triggering published workspace agents, knowledge files, file search and vector stores, the Threads API and thread attachment, plus one short section on ChatGPT workspace usage.

## Structure

- **`package.json`** — Pi package manifest declaring `./skills`.
- **`skills/using-teammate/SKILL.md`** — the single knowledge skill; auto-loads for requests about OpenAI Teammates, workflow.md, or the Teammate API.

## Installation

```bash
# published
pi install npm:@fradser/teammate
# or from this repository
pi install /path/to/pi-packages/packages/teammate
```

## Skills

- **`using-teammate`** — OpenAI Teammates reference: ChatGPT workspace agents, the Workspace Agents API, knowledge files (Files API), file search and vector stores, thread attachment, and ChatGPT workspace usage. Invoke with `/skill:using-teammate`.

## License

MIT.
