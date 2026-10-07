// Serves the report the CLI wrote. One page, no framework: the end-to-end
// test only reads the rendered verdict.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const reportPath = process.env["E2E_REPORT"] ?? path.join(here, ".artifacts", "report.html");

createServer((_request, response) => {
  let body;
  try {
    body = readFileSync(reportPath);
  } catch {
    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end(`No report at ${reportPath}. Run "npm run report" first.`);
    return;
  }
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(body);
}).listen(3000, "127.0.0.1");
