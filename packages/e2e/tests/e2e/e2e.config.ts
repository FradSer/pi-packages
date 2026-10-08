import type { E2EConfig } from "e2e";
import { web } from "@e2e-dev/web";

export default {
  targets: [
    {
      engine: web(process.env.E2E_CDP_ENDPOINT
        ? { connect: { cdpEndpoint: () => process.env.E2E_CDP_ENDPOINT! } }
        : {}),
      app: {
        url: "http://127.0.0.1:3000",
        // The server serves the report the CLI wrote, so the browser test
        // reads real output instead of a fixture page.
        command: { executable: "node", args: ["server.mjs"], log: ".e2e/logs/server.log" },
      },
    },
  ],
} satisfies E2EConfig;
