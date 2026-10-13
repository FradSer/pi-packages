import fs from "node:fs";
import {createHash} from "node:crypto";
import type {ExtensionAPI} from "@earendil-works/pi-coding-agent";
import registerMemory from "../extensions/inject-memory.ts";

export default function(pi: ExtensionAPI): void {
  const file = process.env.PI_MAINTENANCE_SNAPSHOT;
  const bytes = file ? fs.readFileSync(file) : undefined;
  if (bytes && createHash('sha256').update(bytes).digest('hex') !== process.env.PI_MAINTENANCE_SNAPSHOT_SHA256) {
    throw new Error('Frozen maintenance evidence changed');
  }
  const entries = bytes ? JSON.parse(bytes.toString()).entries : undefined;
  if (bytes && !Array.isArray(entries)) throw new Error('Missing frozen maintenance entries');
  registerMemory({...pi, registerCommand(name, options) {
    pi.registerCommand(name, {...options, handler: async (args, ctx) => {
      if (!entries || name !== 'memory') return options.handler(args, ctx);
      const manager = new Proxy(ctx.sessionManager, {get(target, property) {
        if (property === 'getBranch' || property === 'buildContextEntries') return () => structuredClone(entries);
        const member = Reflect.get(target, property);
        return typeof member === 'function' ? member.bind(target) : member;
      }});
      return options.handler(args, {...ctx, sessionManager: manager});
    }});
  }});
  pi.on("session_start", (_event, ctx) => {
    const confirm = ctx.ui.confirm.bind(ctx.ui);
    ctx.ui.confirm = async (...args) => {
      fs.appendFileSync(process.env.PI_MAINTENANCE_EVENTS!, JSON.stringify({kind:'confirm',title:args[0]})+'\n');
      const accepted = await confirm(...args);
      fs.appendFileSync(process.env.PI_MAINTENANCE_EVENTS!, JSON.stringify({kind:'confirmed',accepted})+'\n');
      return accepted;
    };
    fs.writeFileSync(process.env.PI_MAINTENANCE_READY!, "ready");
  });
}
