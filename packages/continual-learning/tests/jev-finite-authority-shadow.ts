/** Research only. Compile an isolated source copy; never mutate production. */
import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import type { createJevJudge } from "../extensions/jev-learning";

export function finiteAuthoritySource(source: string): string {
  const replaceOnce = (before: string, after: string) => {
    if (source.split(before).length !== 2) throw new Error("Frozen source shape changed");
    source = source.replace(before, after);
  };
  const patternLine = String.raw`  const pattern = candidate.rule.bash.replaceAll("[ \t]", "[ \\t]");`;
  replaceOnce(patternLine, '  if (candidate.op === "addRule" && candidate.rule.bash === finiteGitPushMatcher) return "git push";\n' + patternLine);
  const counterMatching = 'matching: `The raw command starts with ${commandWords.split(" ").join(" and ")}, separated by ASCII spaces or tabs. Additional arguments may follow; only a space, tab or absolute command end follows ${commandWords.split(" ").at(-1)}.`, ';
  // Match the line without relying on indentation or trailing whitespace.
  const counter = counterMatching.trimEnd();
  replaceOnce(counter, 'matching: candidate.rule.bash === finiteGitPushMatcher ? finiteGitPushMatching : ' + counter.slice('matching: '.length));
  const family = 'matching: "The raw command starts with these unquoted words, separated by ASCII spaces or tabs. The final word has a word boundary. Additional arguments may follow. Vertical whitespace and Unicode whitespace cannot separate the command words."';
  replaceOnce(family, 'matching: record(candidate) && record(candidate.rule) && candidate.rule.bash === finiteGitPushMatcher ? finiteGitPushMatching : ' + family.slice('matching: '.length));
  return source;
}

export async function loadFiniteAuthorityJudge(): Promise<{
  createJevJudge: typeof createJevJudge; sourceSha256: string; patchedSha256: string; dispose(): Promise<void>;
}> {
  const source = await fs.readFile(new URL("./fixtures/jev-learning-before-bound-scope.ts.txt", import.meta.url), "utf8");
  const patched = finiteAuthoritySource(source);
  const directory = await fs.mkdtemp(new URL("./.jev-finite-authority-", import.meta.url).pathname);
  const dispose = () => fs.rm(directory, { recursive: true, force: true });
  try {
    // Relative dependencies stay inside the owned copy; package resolution uses
    // the same installed workspace SDK. No configuration or proposal is copied.
    await fs.cp(new URL("../extensions/", import.meta.url), `${directory}/extensions`, { recursive: true });
    const file = `${directory}/extensions/jev-learning.ts`;
    await fs.writeFile(file, patched, "utf8");
    const loaded: { createJevJudge: typeof createJevJudge } = await import(file);
    const digest = (text: string) => createHash("sha256").update(text).digest("hex");
    return { createJevJudge: loaded.createJevJudge, sourceSha256: digest(source), patchedSha256: digest(patched), dispose };
  } catch (error) {
    await dispose();
    throw error;
  }
}
