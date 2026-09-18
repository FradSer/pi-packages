/** Pi built-ins available to a bare worker; extension aliases are not inherited. */
export const WORKER_BUILTIN_TOOLS: readonly string[] = [
  "read", "bash", "edit", "write", "grep", "find", "ls", "powershell",
];
