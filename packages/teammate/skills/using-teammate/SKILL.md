---
name: using-teammate
description: >
  Use when building, creating, configuring, setting up, or using an OpenAI
  Teammate — an AI teammate in ChatGPT — including requests that mention
  workflow.md, the Teammate API, workspace agents, knowledge files, file
  search, vector stores, or thread attachment. Reference for the documented
  developer surface: workflow configuration, workspace-agent triggers,
  knowledge files via the Files API, file search and vector stores, and the
  Threads API.
---

# OpenAI Teammates

## Scope and terminology

In OpenAI's current developer documentation, a "teammate" is an AI teammate in the ChatGPT workspace. The Codex use-case guides describe setting up a teammate as a work chief of staff ([Set up a teammate](https://developers.openai.com/codex/use-cases/proactive-teammate)) and as a dedicated project teammate ([Set up a project teammate](https://developers.openai.com/codex/use-cases/project-teammate)). These teammates are ChatGPT workspace agents: shared agents that run repeatable workflows across ChatGPT and independently complete end-to-end tasks ([Building workspace agents in ChatGPT](https://developers.openai.com/cookbook/articles/chatgpt-agents-sales-meeting-prep)).

The developer API surface for teammates documented on developers.openai.com is the Workspace Agents API for triggering published workspace agents ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)), together with the agent-building APIs that supply knowledge and conversation state: the Files API, file search, vector stores, and the Threads API.

**Terminology note.** The current OpenAI API reference defines no `/teammates` resource: there is no teammate endpoint group in the API reference. Requests that mention a Teammate API endpoint map to the Workspace Agents API and the agent-building APIs documented below. Likewise, the current developer documentation does not define a `workflow.md` file format; workflow configuration for teammates is expressed through the surfaces described in the next section. Do not assume undocumented endpoints or file formats.

## Teammates in the ChatGPT workspace

ChatGPT workspace agents are available in research preview for ChatGPT Business, Enterprise, and Edu customers; they are evolutions of GPTs that can work across tools to complete high-value tasks, and they can use connected apps, follow skills, run on a schedule, and be shared with colleagues in the workspace ([Building workspace agents in ChatGPT](https://developers.openai.com/cookbook/articles/chatgpt-agents-sales-meeting-prep)). The Codex use-case guides show two teammate configurations: a work chief of staff that checks connected messages, email, calendar, documents, and project trackers on an hourly schedule ([Set up a teammate](https://developers.openai.com/codex/use-cases/proactive-teammate)), and a project teammate with a dedicated task for one project or workstream that reviews relevant sources, tracks meaningful changes on a schedule, prepares the next step, and waits for approval before taking action ([Set up a project teammate](https://developers.openai.com/codex/use-cases/project-teammate)). Both guides ship a starter prompt and name the connected work tools the teammate may review.

## Workflow as code

The current developer documentation does not document a `workflow.md` file. Workflow configuration for teammates is expressed through the documented surfaces below, and those are the surfaces to use:

- **Workspace agents in ChatGPT.** Agents are created through a conversational builder, given access to the team's connected apps and knowledge bases, tested before publishing, scheduled to run on a recurring schedule, and shared with the workspace ([Building workspace agents in ChatGPT](https://developers.openai.com/cookbook/articles/chatgpt-agents-sales-meeting-prep)).
- **The Workspace Agents API.** The programmatic entry point: a trigger request carries the message text passed to the agent and an optional caller-defined conversation key that continues the same conversation across trigger events ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Agent Builder workflows.** Agent Builder is a visual canvas for building multi-step agent workflows; a workflow is a combination of agents, tools, and control-flow logic that encapsulates the steps and actions for handling a task, and it is published as an object with an ID and versioning. Note that OpenAI is deprecating Agent Builder and schedules the product to shut down on November 30, 2026 ([Agent Builder](https://developers.openai.com/api/docs/guides/agent-builder)).

## Workspace Agents API

The Workspace Agents API triggers a published ChatGPT workspace agent from an external system or automation ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).

- **Endpoints.** `POST https://api.chatgpt.com/v1/workspace_agents/{id}/trigger` starts a run; `GET https://api.chatgpt.com/v1/workspace_agents/{id}/runs/{run_id}` polls run status ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Identifiers.** `id` is the stable public API trigger identifier for the published API channel, in an `agtch_XXX` format; `run_id` is the trigger run identifier returned by a trigger request, in an `apirun_XXX` format ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Authentication.** Authenticate with a Workspace Agent access token as a bearer credential on `api.chatgpt.com` ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs), [Authenticate with Workspace Agent access tokens](https://developers.openai.com/workspace-agents/authentication)).
- **Request body.** `input` (string, required): message text passed to the agent as trigger input. `conversation_key` (string, optional): a caller-defined stable identifier for continuing the same agent conversation across multiple trigger events. To safely retry the same trigger event, send an optional `Idempotency-Key` header and reuse the same key only when retrying the same event; a retried request with the same key returns the original accepted outcome instead of adding a second trigger event to the queue ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Response.** The API durably queues the trigger event and returns `202 Accepted` with a `conversation_url` link to the ChatGPT conversation, for example `{ "conversation_url": "https://chatgpt.com/c/123" }`. The agent's response cannot currently be retrieved through the API ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Run status polling (beta).** Include the header `OpenAI-Beta: workspace_agent_runs=v1` when triggering to receive an `agent_trigger_run_id` in the trigger response, then poll the run endpoint until a terminal status. The run object is `workspace_agent.trigger_run` with `id`, `status`, `created_at`, `agent_id`, `api_trigger_id`, `conversation_url`, and `error`; status values are `queued`, `in_progress`, `suspended`, `completed`, and `failed`, where `completed` and `failed` are terminal ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).

**Workspace Agent access tokens.** Tokens are provisioned from the ChatGPT admin access-token flow and are scoped for workspace use. A workspace admin must first enable workspace agents and turn on "Allow users to create personal access tokens" in Admin > Permissions & roles, then create an access token in Admin > Access tokens with the **Workspace Agents** scope. The token is used as a bearer credential and is scoped to Workspace Agents API operations only ([Authenticate with Workspace Agent access tokens](https://developers.openai.com/workspace-agents/authentication)).

## Knowledge files: the Files API

Files are used to upload documents that can be used with features like Assistants and Fine-tuning ([Files](https://developers.openai.com/api/reference/resources/files)).

### FileObject

The `File` object represents a document that has been uploaded to OpenAI ([Files](https://developers.openai.com/api/reference/resources/files)). The live `FileObject` schema lists these fields:

- `id` — string; the file identifier, which can be referenced in API endpoints.
- `bytes` — number; the size of the file, in bytes.
- `created_at` — number; the Unix timestamp (in seconds) for when the file was created.
- `filename` — string; the name of the file.
- `object` — always `"file"`.
- `purpose` — the intended purpose of the file: `assistants`, `assistants_output`, `batch`, `batch_output`, `fine-tune`, `fine-tune-results`, `vision`, or `user_data`.
- `status`, `expires_at`, and `status_details` — documented on the current schema and marked deprecated.

The schema exposes the file length through `bytes`; there is no separate size field on `FileObject` ([Files](https://developers.openai.com/api/reference/resources/files)).

### POST /files

Upload a file as multipart form data with `file` (the File object, not the file name) and `purpose`, plus an optional `expires_after` object with `anchor` and `seconds`. Documented `purpose` values for upload are `assistants`, `batch`, `fine-tune`, `vision`, `user_data`, and `evals`. Individual files can be up to 512 MB, each project can store up to 2.5 TB of files in total, there is no organization-wide storage limit, and uploads to this endpoint are rate-limited to 1,000 requests per minute per authenticated user. The Assistants API supports files up to 2 million tokens and of specific file types; the Fine-tuning and Batch APIs only support `.jsonl` files. Vector store attachment has separate limits, including 2,000 attached files per minute per organization ([Upload file](https://developers.openai.com/api/reference/resources/files/methods/create)).

### GET /files and related endpoints

- `GET /files` lists files. The optional `purpose` query parameter limits the list to files with the given purpose; pagination is controlled by `limit` (1 to 10,000, default 10,000), `order` (asc or desc by the `created_at` timestamp), and `after`. The response `data` field is an array of `FileObject` ([List files](https://developers.openai.com/api/reference/resources/files/methods/list)).
- `GET /files/{file_id}` retrieves a file as a `FileObject` ([Retrieve file](https://developers.openai.com/api/reference/resources/files/methods/retrieve)).
- `DELETE /files/{file_id}` deletes a file and returns a `FileDeleted` object with `id`, `deleted`, and `object` ([Delete file](https://developers.openai.com/api/reference/resources/files/methods/delete)).

## File search and vector stores

File search is a tool available in the Responses API. It enables models to retrieve information in a knowledge base of previously uploaded files through semantic and keyword search; by creating vector stores and uploading files to them, you give the model access to these knowledge bases, or vector stores. It is a hosted tool managed by OpenAI, so no code is required to handle its execution ([File search](https://developers.openai.com/api/docs/guides/tools-file-search)).

A vector store is a collection of processed files used by the `file_search` tool ([Vector Stores](https://developers.openai.com/api/reference/resources/vector_stores)). Adding a file to a vector store automatically parses, chunks, embeds, and stores the file in a vector database capable of both keyword and semantic search; each vector store can hold up to 10,000 files, and for vector stores created starting in November 2025 the limit is 100,000,000 files. Vector stores can be attached to both assistants and threads, at most one per assistant and at most one per thread ([File Search tool](https://developers.openai.com/api/docs/assistants/tools/file-search)). By default `max_chunk_size_tokens` is 800 and `chunk_overlap_tokens` is 400; chunking is configurable per file through `chunking_strategy`, where `max_chunk_size_tokens` must be between 100 and 4096 inclusive. The maximum file size is 512 MB and each file should contain no more than 5,000,000 tokens ([File Search tool](https://developers.openai.com/api/docs/assistants/tools/file-search)).

Vector Stores endpoints, all documented in the reference ([Vector Stores](https://developers.openai.com/api/reference/resources/vector_stores)):

- `POST /vector_stores` — create a vector store ([Create vector store](https://developers.openai.com/api/reference/resources/vector_stores/methods/create)).
- `GET /vector_stores` — list vector stores ([List vector stores](https://developers.openai.com/api/reference/resources/vector_stores/methods/list)).
- `GET /vector_stores/{vector_store_id}` — retrieve a vector store ([Retrieve vector store](https://developers.openai.com/api/reference/resources/vector_stores/methods/retrieve)).
- `POST /vector_stores/{vector_store_id}` — modify a vector store ([Modify vector store](https://developers.openai.com/api/reference/resources/vector_stores/methods/update)).
- `DELETE /vector_stores/{vector_store_id}` — delete a vector store ([Delete vector store](https://developers.openai.com/api/reference/resources/vector_stores/methods/delete)).
- `POST /vector_stores/{vector_store_id}/search` — search a vector store for relevant chunks based on a query and file attributes filter. The body takes `query` (a string or array of strings) and an optional `filters` value, either a `ComparisonFilter` with an operator (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `nin`) or a `CompoundFilter`; results are returned as `vector_store.search_results.page` objects with `file_id`, `filename`, `score`, `attributes`, `content`, `has_more`, and `next_page` ([Search vector store](https://developers.openai.com/api/reference/resources/vector_stores/methods/search)).
- Subresources for adding files: vector store files ([Vector Store Files](https://developers.openai.com/api/reference/resources/vector_stores/subresources/files), [Create vector store file](https://developers.openai.com/api/reference/resources/vector_stores/subresources/files/methods/create)) and vector store file batches for attaching many files in one request ([Vector Store File Batches](https://developers.openai.com/api/reference/resources/vector_stores/subresources/file_batches), [Create vector store file batch](https://developers.openai.com/api/reference/resources/vector_stores/subresources/file_batches/methods/create)).

## Threads and thread attachment

Threads and messages represent a conversation session between an assistant and a user ([Assistants API deep dive](https://developers.openai.com/api/docs/assistants/deep-dive)). The Threads API is documented in the Beta Threads reference group ([Threads](https://developers.openai.com/api/reference/resources/beta/subresources/threads)) and belongs to the Assistants API, which the reference labels as deprecated in favor of the Responses API ([Create thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create)).

### POST /threads

`POST /threads` creates a thread ([Create thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create)). The documented request body:

- `messages` — optional array of objects with `content`, `role`, `attachments`, and `metadata`: a list of messages to start the thread with.
  - `content` — string, or an array of content parts: `TextContentBlockParam` with `text` and `type` (`"text"`), `ImageFileContentBlock` with `image_file` and `type` (`"image_file"`), or `ImageURLContentBlock` with `image_url` and `type` (`"image_url"`).
  - `role` — `"user"` or `"assistant"`.
  - `attachments` — optional array of objects with `file_id` (optional string) and `tools` (optional array of `CodeInterpreterTool` with `type` `"code_interpreter"` or `FileSearchTool` with `type` `"file_search"`), or null: the files attached to the message and the tools they should be added to.
  - `metadata` — a set of up to 16 key-value pairs; keys have a maximum length of 64 characters and values a maximum length of 512 characters.
- `tool_resources` — optional object with `code_interpreter.file_ids` (a list of file IDs, up to 20 files) and `file_search.vector_store_ids` (up to 1 vector store attached to the thread), or the `file_search.vector_stores` helper that creates a vector store from `file_ids` and attaches it to the thread, with an optional `chunking_strategy` (`auto`, or `static` with `max_chunk_size_tokens` and `chunk_overlap_tokens`).

The response is a `Thread` object with `id`, `created_at`, `metadata`, `object` (`"thread"`), and `tool_resources` ([Create thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create)).

### Limits and truncation

There is a limit of 100,000 messages per thread. Once the size of the messages exceeds the context window of the model, the thread attempts smart truncation — the documentation describes the thread attempting to "smartly truncate" messages — before fully dropping the messages it considers the least important ([Assistants API deep dive](https://developers.openai.com/api/docs/assistants/deep-dive)).

### Thread and message endpoints

- Threads: create ([Create thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create)), retrieve ([Retrieve thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/retrieve)), modify ([Modify thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/update)), and delete ([Delete thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/delete)).
- Messages: create ([Create message](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/messages/methods/create)), list ([List messages](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/messages/methods/list)), plus retrieve, update, and delete ([Messages](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/messages)).
- Runs, run steps, and tool outputs are documented under the thread runs resource ([Runs](https://developers.openai.com/api/reference/resources/beta/subresources/threads/subresources/runs)).

## API stability and availability

Mirror the documentation's own labeling when describing these surfaces:

- **Workspace agents** — research preview for ChatGPT Business, Enterprise, and Edu customers ([Building workspace agents in ChatGPT](https://developers.openai.com/cookbook/articles/chatgpt-agents-sales-meeting-prep)).
- **Run status polling** — in beta, opt-in via the `OpenAI-Beta: workspace_agent_runs=v1` header ([Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)).
- **Threads, Messages, and Runs** — Beta Threads reference group; the Assistants API is deprecated in favor of the Responses API ([Threads](https://developers.openai.com/api/reference/resources/beta/subresources/threads), [Create thread](https://developers.openai.com/api/reference/resources/beta/subresources/threads/methods/create)).
- **FileObject** — `status`, `expires_at`, and `status_details` are marked deprecated on the current schema ([Files](https://developers.openai.com/api/reference/resources/files)).
- **Agent Builder** — deprecated and scheduled to shut down on November 30, 2026 ([Agent Builder](https://developers.openai.com/api/docs/guides/agent-builder)).
