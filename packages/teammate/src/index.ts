/**
 * @fradser/teammate — Pi extension for multi-agent teams.
 *
 * Provides a mailbox-based communication system, task management,
 * and team-leader orchestration for Pi agents.
 *
 * Tools registered:
 *   teammate_register      — Register a new teammate agent
 *   teammate_list          — List all registered teammates
 *   teammate_send          — Send a message to a teammate's mailbox
 *   teammate_read_mailbox  — Read messages from a teammate's mailbox
 *   teammate_assign_task   — Assign a task to a teammate (team-leader only)
 *   teammate_list_tasks    — List tasks by status/assignee
 *   teammate_update_task   — Update task status (start, complete, fail)
 *   teammate_broadcast     — Broadcast to all teammates (team-leader only)
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  EmptyParams,
  TeammateAssignTaskParams,
  TeammateBroadcastParams,
  TeammateListTasksParams,
  TeammateReadMailboxParams,
  TeammateRegisterParams,
  TeammateSendParams,
  TeammateSpawnParams,
  TeammateTaskDepsParams,
  TeammateUpdateTaskParams,
  type TeammateRole,
} from "./types";
import {
  createTask,
  getTeammate,
  getTeamLeaders,
  getTeammatesByRole,
  getUnreadCount,
  isTaskReady,
  listTasks,
  listTeammates,
  markTeammateIdle,
  markTeammateRunning,
  persistState,
  readMailbox,
  registerTeammate,
  sendMessage,
  setSpawnInfo,
  setTaskDeps,
  tryRestoreState,
  updateTaskStatus,
  getSummary,
} from "./state";
import { spawnPiWorker } from "./spawner";
import { captureWorktreeDiff, cleanupWorktree, createWorktree, discardWorktree } from "./worktree";

const TEAMMATE_GUIDANCE = `
## Teammate System

You have access to a teammate multi-agent system (mailbox, tasks, team-leader orchestration).
Use it when:
- Delegating work to specialized sub-agents (register workers, assign tasks)
- Tracking progress across multiple parallel workstreams
- Sending async instructions or broadcast updates to team members
- Requesting review or handoff between agents

When you need to use it, consult /skill:using-teammate for the full tool reference.
`;

export default function (pi: ExtensionAPI) {
  // ── Session lifecycle ───────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    const restored = tryRestoreState(ctx.sessionManager);
    if (restored) {
      const summary = getSummary();
      ctx.ui.setStatus("teammate", summary);
    }
  });

  pi.on("session_shutdown", async () => {
    persistState(pi);
  });

  pi.on("turn_end", async () => {
    persistState(pi);
  });

  // ── Inject teammate guidance into system prompt ─────────────────

  pi.on("before_agent_start", async (event) => {
    return {
      systemPrompt: event.systemPrompt + TEAMMATE_GUIDANCE,
    };
  });

  // ── Tools ───────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_register",
    label: "Register Teammate",
    description: [
      "Register a new teammate agent with a name, role, and description.",
      "Roles: team-leader (orchestrator), worker (executor), reviewer (code review), specialist (domain expert), observer (read-only).",
      "The first registered teammate with role 'team-leader' becomes the default orchestrator.",
    ].join(" "),
    parameters: TeammateRegisterParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = registerTeammate({
        name: params.name,
        role: params.role as TeammateRole,
        description: params.description,
        model: params.model,
        tools: params.tools,
        registeredAt: Date.now(),
      });

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to register teammate." }],
          details: {},
          isError: true,
        };
      }

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      const isLeader = params.role === "team-leader";
      return {
        content: [
          {
            type: "text",
            text: [
              `Registered teammate "${params.name}" (role: ${params.role}).`,
              isLeader ? `${params.name} is the team leader and can assign tasks and broadcast messages.` : "",
              "",
              `Registered teammates: ${listTeammates().map((t) => `${t.name} (${t.role})`).join(", ")}`,
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list",
    label: "List Teammates",
    description: "List all registered teammates with their roles and descriptions.",
    parameters: EmptyParams,

    async execute() {
      const teammates = listTeammates();
      if (teammates.length === 0) {
        return {
          content: [{ type: "text", text: "No teammates registered yet. Use teammate_register to add one." }],
          details: {},
        };
      }

      const lines: string[] = ["## Registered Teammates\n"];
      for (const t of teammates) {
        const unread = getUnreadCount(t.name);
        const liveness =
          t.status === "running"
            ? `\u25CF running${t.currentTaskId ? ` (task ${t.currentTaskId})` : ""}`
            : "idle";
        lines.push(`- **${t.name}** (${t.role}) [${liveness}]`);
        lines.push(`  ${t.description}`);
        if (unread > 0) lines.push(`  - ${unread} unread message(s)`);
        if (t.model) lines.push(`  Model: ${t.model}`);
        if (t.tools && t.tools.length > 0) lines.push(`  Tools: ${t.tools.join(", ")}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_send",
    label: "Send Message",
    description: "Send a message to a teammate's mailbox. The recipient can read it with teammate_read_mailbox.",
    parameters: TeammateSendParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const recipient = getTeammate(params.to);
      if (!recipient) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${params.to}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const sender = "agent";

      const msg = sendMessage({
        from: sender,
        to: params.to,
        subject: params.subject,
        body: params.body,
        taskId: params.taskId,
      });

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      return {
        content: [
          {
            type: "text",
            text: `Message sent to "${params.to}".\nSubject: ${params.subject}\nMessage ID: ${msg.id}`,
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_read_mailbox",
    label: "Read Mailbox",
    description: "Read messages from a teammate's mailbox. Optionally mark as read or filter to unread only.",
    parameters: TeammateReadMailboxParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const name = params.name ?? "agent";
      const teammate = getTeammate(name);
      if (!teammate) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${name}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const messages = readMailbox(name, {
        unreadOnly: params.unreadOnly ?? true,
        markRead: params.markRead ?? true,
      });

      if (messages.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: `No ${params.unreadOnly !== false ? "unread " : ""}messages in "${name}"'s mailbox.`,
            },
          ],
          details: {},
        };
      }

      const lines: string[] = [
        `## Mailbox: ${name} (${messages.length} message${messages.length > 1 ? "s" : ""})\n`,
      ];
      for (const msg of messages) {
        lines.push(`### [${msg.id}] ${msg.subject}`);
        lines.push(`From: ${msg.from} | ${new Date(msg.timestamp).toLocaleString()}`);
        if (msg.taskId) lines.push(`Task: ${msg.taskId}`);
        lines.push("");
        lines.push(msg.body);
        lines.push("");
        lines.push("---");
        lines.push("");
      }

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_assign_task",
    label: "Assign Task",
    description: [
      "Assign a task to a teammate. Only teammates with the 'team-leader' role can assign tasks.",
      "The assignee will see the task in their task list and receive a mailbox notification.",
    ].join(" "),
    parameters: TeammateAssignTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const assignee = getTeammate(params.assignee);
      if (!assignee) {
        return {
          content: [
            {
              type: "text",
              text: `Teammate "${params.assignee}" not found. Register them first with teammate_register.`,
            },
          ],
          details: {},
          isError: true,
        };
      }

      const leaders = getTeamLeaders();
      if (leaders.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: [
                "No team-leader registered. A team-leader must be registered first to assign tasks.",
                "Register a team-leader with: teammate_register name='...' role='team-leader' description='...'",
              ].join("\n"),
            },
          ],
          details: {},
          isError: true,
        };
      }

      const created = createTask(params.title, params.description, params.assignee, "team-leader");
      if (!created.ok || !created.task) {
        return {
          content: [{ type: "text", text: created.error ?? "Failed to create task." }],
          details: {},
          isError: true,
        };
      }
      const task = created.task;

      sendMessage({
        from: "team-leader",
        to: params.assignee,
        subject: `New task: ${params.title}`,
        body: `You have been assigned a new task.\n\nTitle: ${params.title}\nDescription: ${params.description}\n\nTask ID: ${task.id}`,
        taskId: task.id,
      });

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      return {
        content: [
          {
            type: "text",
            text: [
              `Task assigned to "${params.assignee}".`,
              `Task ID: ${task.id}`,
              `Title: ${params.title}`,
              `Status: assigned`,
              "",
              `${params.assignee} has been notified via mailbox.`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_list_tasks",
    label: "List Tasks",
    description: "List tasks, optionally filtered by status or assignee.",
    parameters: TeammateListTasksParams,

    async execute(_toolCallId, params) {
      const tasks = listTasks({
        status: params.status,
        assignee: params.assignee,
      });

      if (tasks.length === 0) {
        let msg = "No tasks found.";
        if (params.status) msg += ` Status: ${params.status}.`;
        if (params.assignee) msg += ` Assignee: ${params.assignee}.`;
        return { content: [{ type: "text", text: msg }], details: {} };
      }

      const lines: string[] = ["## Tasks\n"];
      for (const task of tasks) {
        const statusIcon =
          task.status === "completed"
            ? "\u2713"
            : task.status === "failed"
              ? "\u2717"
              : task.status === "in_progress"
                ? "\u22EF"
                : task.status === "cancelled"
                  ? "\u2212"
                  : "\u25CB";
        lines.push(`### ${statusIcon} [${task.id}] ${task.title}`);
        lines.push(`Assignee: ${task.assignee} | Status: ${task.status}`);
        if (task.spawn) {
          const spawn = task.spawn;
          const stateLabel = spawn.status === "running" ? "running (pid " + spawn.pid + ")" : spawn.status;
          lines.push(`Spawn: ${stateLabel}`);
          if (spawn.timedOut) lines.push(`Timed out: yes`);
          if (spawn.usage) {
            const u = spawn.usage;
            lines.push(`Usage: ${u.totalTokens} tokens (in ${u.input} / out ${u.output}) | cost $${u.cost}`);
          }
        }
        if (task.blockedBy.length > 0) lines.push(`Blocked by: ${task.blockedBy.join(", ")}`);
        if (task.blocks.length > 0) lines.push(`Blocks: ${task.blocks.join(", ")}`);
        lines.push(task.description);
        if (task.result) lines.push(`Result: ${task.result}`);
        if (task.errorMessage) lines.push(`Error: ${task.errorMessage}`);
        lines.push(`Created: ${new Date(task.createdAt).toLocaleString()}`);
        if (task.completedAt) lines.push(`Completed: ${new Date(task.completedAt).toLocaleString()}`);
        lines.push("");
      }

      return { content: [{ type: "text", text: lines.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_update_task",
    label: "Update Task",
    description: "Update a task's status — mark as in_progress, completed, failed, or cancelled.",
    parameters: TeammateUpdateTaskParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const result = updateTaskStatus(params.taskId, params.status, params.result, params.errorMessage);

      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to update task." }],
          details: {},
          isError: true,
        };
      }

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      const task = result.task!;
      return {
        content: [
          {
            type: "text",
            text: [
              `Task [${task.id}] "${task.title}" updated to status: ${task.status}.`,
              task.result ? `Result: ${task.result}` : "",
              task.errorMessage ? `Error: ${task.errorMessage}` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_broadcast",
    label: "Broadcast",
    description: [
      "Broadcast a message to all teammates (or filter by role).",
      "Only usable when a team-leader is registered.",
    ].join(" "),
    parameters: TeammateBroadcastParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const leaders = getTeamLeaders();
      if (leaders.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: "No team-leader registered. A team-leader must be registered first to broadcast.",
            },
          ],
          details: {},
          isError: true,
        };
      }

      let recipients = params.role
        ? getTeammatesByRole(params.role)
        : listTeammates().filter((t) => t.role !== "team-leader");

      if (!params.role) {
        recipients = listTeammates();
      }

      if (recipients.length === 0) {
        return {
          content: [
            {
              type: "text",
              text: params.role
                ? `No teammates found with role "${params.role}".`
                : "No teammates registered to broadcast to.",
            },
          ],
          details: {},
          isError: true,
        };
      }

      for (const recipient of recipients) {
        sendMessage({
          from: "team-leader",
          to: recipient.name,
          subject: `Broadcast: ${params.subject}`,
          body: params.body,
        });
      }

      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      return {
        content: [
          {
            type: "text",
            text: [
              `Broadcast sent to ${recipients.length} teammate(s).`,
              `Subject: ${params.subject}`,
              params.role ? `(filtered by role: ${params.role})` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_task_deps",
    label: "Set Task Dependencies",
    description: [
      "Wire task dependencies on the board: which tasks block this one (blockedBy)",
      "and which tasks this one blocks (blocks). A task cannot be spawned until",
      "every blockedBy task is completed or cancelled.",
    ].join(" "),
    parameters: TeammateTaskDepsParams,

    async execute(_toolCallId, params) {
      const result = setTaskDeps(params.taskId, {
        blocks: params.blocks,
        blockedBy: params.blockedBy,
      });
      if (!result.ok) {
        return {
          content: [{ type: "text", text: result.error ?? "Failed to update task dependencies." }],
          details: {},
          isError: true,
        };
      }
      const task = listTasks().find((t) => t.id === params.taskId);
      const parts = [`Task [${params.taskId}] dependencies updated.`];
      if (task) {
        if (task.blockedBy.length > 0) parts.push(`Blocked by: ${task.blockedBy.join(", ")}`);
        if (task.blocks.length > 0) parts.push(`Blocks: ${task.blocks.join(", ")}`);
      }
      return { content: [{ type: "text", text: parts.join("\n") }], details: {} };
    },
  });

  // ─────────────────────────────────────────────────────────────────

  pi.registerTool({
    name: "teammate_spawn",
    label: "Spawn Teammate",
    description: [
      "Spawn a real child Pi process as the teammate to execute a task.",
      "The worker runs with its own model and tool scope in non-interactive mode.",
      "The task must be ready: every blockedBy task must be completed or cancelled.",
      "The task status and spawn info are updated when the worker finishes.",
    ].join(" "),
    parameters: TeammateSpawnParams,

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const teammate = getTeammate(params.name);
      if (!teammate) {
        return {
          content: [{ type: "text", text: `Teammate "${params.name}" not found. Register them first with teammate_register.` }],
          details: {},
          isError: true,
        };
      }
      const task = listTasks().find((t) => t.id === params.taskId);
      if (!task) {
        return {
          content: [{ type: "text", text: `Task "${params.taskId}" not found.` }],
          details: {},
          isError: true,
        };
      }
      const readiness = isTaskReady(params.taskId);
      if (!readiness.ready) {
        return {
          content: [
            {
              type: "text",
              text: [
                `Task "${params.taskId}" is not ready: blocked by ${readiness.unmet.join(", ")}.`, 
                "Complete or cancel those tasks first, or rewire deps with teammate_task_deps.",
              ].join(" "),
            },
          ],
          details: {},
          isError: true,
        };
      }

      // Optional git worktree isolation: run the worker on its own branch.
      let worktree: ReturnType<typeof createWorktree> | undefined;
      if (params.isolation === "worktree") {
        worktree = createWorktree(ctx.cwd, params.taskId);
        if ("error" in worktree) {
          return {
            content: [{ type: "text", text: `Cannot isolate worker: ${worktree.error}` }],
            details: {},
            isError: true,
          };
        }
      }

      markTeammateRunning(params.name, params.taskId);

      const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;
      const timeoutMs = params.timeoutMs ?? DEFAULT_TIMEOUT_MS;

      const started = spawnPiWorker({
        description: task.description,
        model: teammate.model,
        tools: teammate.tools,
        cwd: worktree && !("error" in worktree) ? worktree.cwd : ctx.cwd,
        signal: ctx.signal,
        timeoutMs,
        onExit: ({ pid, exitCode, stdout, stderr, usage, timedOut }) => {
          let patchText = "";
          if (worktree && !("error" in worktree)) {
            const diff = captureWorktreeDiff(worktree);
            if (diff.patch.trim()) {
              patchText = `\n\n=== Worktree changes ===\n${diff.diffStat}\n\n${diff.patch}`;
            }
            cleanupWorktree(worktree);
          }
          const ok = exitCode === 0 && !timedOut;
          setSpawnInfo(params.taskId, {
            pid,
            status: ok ? "completed" : "failed",
            startedAt: task.spawn?.startedAt ?? Date.now(),
            finishedAt: Date.now(),
            exitCode,
            stdout: ok ? stdout + patchText : undefined,
            stderr: ok ? undefined : stderr,
            usage,
            timedOut,
            error: ok
              ? undefined
              : timedOut
                ? `Worker timed out after ${Math.round(timeoutMs / 1000)}s.`
                : `Worker exited with code ${exitCode}.`,
          });
          markTeammateIdle(params.name);
          persistState(pi);
          ctx.ui.setStatus("teammate", getSummary());
        },
        onError: (error) => {
          setSpawnInfo(params.taskId, {
            pid: 0,
            status: "failed",
            startedAt: task.spawn?.startedAt ?? Date.now(),
            finishedAt: Date.now(),
            error: error.message,
          });
          markTeammateIdle(params.name);
          if (worktree && !("error" in worktree)) discardWorktree(worktree);
          persistState(pi);
          ctx.ui.setStatus("teammate", getSummary());
        },
      });

      if ("error" in started) {
        markTeammateIdle(params.name);
        if (worktree && !("error" in worktree)) discardWorktree(worktree);
        return {
          content: [{ type: "text", text: `Failed to spawn worker: ${started.error}` }],
          details: {},
          isError: true,
        };
      }

      setSpawnInfo(params.taskId, {
        pid: started.pid,
        status: "running",
        startedAt: Date.now(),
      });
      task.status = "in_progress";
      persistState(pi);
      ctx.ui.setStatus("teammate", getSummary());

      const isolationNote =
        params.isolation === "worktree" && worktree && !("error" in worktree)
          ? `Isolation: worktree ${worktree.path} (branch ${worktree.branch})`
          : "Isolation: none";
      return {
        content: [
          {
            type: "text",
            text: [
              `Spawned "${params.name}" as a worker for task [${params.taskId}] "${task.title}".`,
              `PID: ${started.pid} | Model: ${teammate.model ?? "default"} | Status: running`, 
              isolationNote,
              `The task will be marked completed/failed when the worker finishes.`,
            ].join("\n"),
          },
        ],
        details: {},
      };
    },
  });

  // ── Command for debugging ────────────────────────────────────────

  pi.registerCommand("teammate-status", {
    description: "Show teammate system status summary",
    handler: async (_args, ctx) => {
      const teammates = listTeammates();
      const tasks = listTasks();

      ctx.ui.notify(
        [
          `Teammates: ${teammates.length}`,
          `Tasks: ${tasks.length} (${tasks.filter((t) => t.status === "in_progress" || t.status === "assigned").length} active)`,
          `Unread messages: ${teammates.reduce((sum, t) => sum + getUnreadCount(t.name), 0)}`,
        ].join(" | "),
        "info",
      );
    },
  });
}