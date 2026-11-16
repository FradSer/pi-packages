import { activeRecord } from "../src/records.ts";

const cwd = process.argv[2];
if (!cwd) throw new Error("Usage: non-git-probe.mts <cwd>");

const record = activeRecord(cwd);
if (record !== undefined) throw new Error(`Expected no SDLC record outside a Git checkout, got ${record}`);
