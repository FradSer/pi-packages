export function sessionRoute(name: string): string {
  return `session:${name}`;
}

export function resolveRecipient(
  to: string,
  roster: ReadonlyArray<{ name: string; agent: string; status: string }>,
): string {
  const living = roster.filter((entry) => entry.status !== "stopped");
  const explicit = to.startsWith("session:");
  const name = explicit ? to.slice("session:".length) : to;
  const recipients = living.filter((entry) => entry.name === name || (!explicit && entry.agent === to));
  if (recipients.length > 1) {
    throw new Error(`Ambiguous Agent @${to}. Use a precise route: ${recipients.map((entry) => sessionRoute(entry.name)).join(", ")}.`);
  }
  if (recipients.length === 1) return recipients[0].name;
  throw new Error(`No living teammate named "${to}".`);
}
