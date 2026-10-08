#!/bin/sh
# Packed E2E/kit tarballs, isolated Pi 1.0.4, scripted native acceptance.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
receipt_dir=$(mktemp -d "${TMPDIR:-/tmp}/e2e-docker-XXXXXXXX")
container_name="e2e-isolated-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"
pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/e2e pack --pack-destination "$receipt_dir" > "$receipt_dir/e2e-pack.log"
cat > "$receipt_dir/setup.sh" <<'SETUP'
#!/bin/sh
set -eu
corepack enable
mkdir -p /isolated /verify/packages/e2e/tests
printf '%s\n' '{"private":true,"type":"module"}' > /verify/package.json
cd /isolated
set -- /receipts/fradser-pi-kit-*.tgz
export TASK_KIT_TARBALL="$1"
set -- /receipts/fradser-pi-e2e-*.tgz
export E2E_TARBALL="$1"
node --input-type=module <<'JSON'
import { writeFileSync } from "node:fs";
const kit = `file:${process.env.TASK_KIT_TARBALL}`;
writeFileSync("package.json", JSON.stringify({
  name: "isolated-e2e-verification", private: true, type: "module", packageManager: "pnpm@11.21.0",
  dependencies: {
    "@earendil-works/pi-coding-agent": "1.0.4", "@earendil-works/pi-ai": "1.0.4", "@earendil-works/pi-tui": "1.0.4",
    "@fradser/pi-kit": kit, "@fradser/pi-e2e": `file:${process.env.E2E_TARBALL}`,
    tsx: "^4.19.0", "@babel/parser": "^7.29.9", typebox: "^1.3.12",
  },
}));
JSON
cat > pnpm-workspace.yaml <<'YAML'
packages:
  - '.'
overrides:
  '@earendil-works/chord': 1.0.4
  '@earendil-works/pi-agent-core': 1.0.4
  '@earendil-works/pi-ai': 1.0.4
  '@earendil-works/pi-codemode': 1.0.4
  '@earendil-works/pi-mcp': 1.0.4
  '@earendil-works/pi-tui': 1.0.4
allowBuilds:
  esbuild: true
  '@google/genai': true
  protobufjs: true
YAML
node --input-type=module <<'OVERRIDE'
import { readFileSync, writeFileSync } from "node:fs";
const yaml = readFileSync("pnpm-workspace.yaml", "utf8");
writeFileSync("pnpm-workspace.yaml", yaml.replace("overrides:\n",
  `overrides:\n  '@fradser/pi-kit': ${JSON.stringify(`file:${process.env.TASK_KIT_TARBALL}`)}\n`));
OVERRIDE
pnpm install
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null
python3 -m venv /verify/venv
/verify/venv/bin/pip install -q pyte pytest
cp -R /e2e-tests/. /verify/packages/e2e/tests/
cp /root-agents /verify/AGENTS.md
mkdir -p /verify/tests/e2e /verify/packages/goal /verify/packages/tasks /verify/.e2e
cp /runner-config /verify/.e2e/runner.json
cp /root-manifest /verify/package.json
cp /root-lockfile /verify/pnpm-lock.yaml
cp -R /goal-source /verify/packages/goal/src
cp /goal-entry /verify/packages/goal/index.ts
cp /goal-manifest /verify/packages/goal/package.json
cp -R /goal-tests /verify/packages/goal/tests
cp -R /task-source /verify/packages/tasks/src
cp -R /task-tests /verify/packages/tasks/tests
cp -R /shared-support /verify/tests/e2e/support
ln -s /goal-features /verify/packages/goal/features
ln -s /task-features /verify/packages/tasks/features
for entry in src extensions features examples index.ts LICENSE README.md README.zh-CN.md TUI.zh-CN.md; do
  ln -s "/isolated/node_modules/@fradser/pi-e2e/$entry" "/verify/packages/e2e/$entry"
done
# Static workspace manifest assertions use the source manifest; executable
# code, features, docs and normal Pi autoload use the installed tarball.
cp /source-manifest /verify/packages/e2e/package.json
cp /package-agents /verify/packages/e2e/AGENTS.md
mkdir -p /verify/packages/kit
cp -R /isolated/node_modules/@fradser/pi-kit/src /verify/packages/kit/src
cp /isolated/node_modules/@fradser/pi-kit/index.ts /verify/packages/kit/index.ts
cp /isolated/node_modules/@fradser/pi-kit/package.json /verify/packages/kit/package.json
ln -s /isolated/node_modules /verify/node_modules
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent
printf '%s\n' '{"packages":["/isolated/node_modules/@fradser/pi-e2e"]}' > /isolated/agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list
pi --version
export PATH="/verify/venv/bin:$PATH"
export NODE_OPTIONS=--import=/isolated/node_modules/tsx/dist/loader.mjs
cd /verify
PI_OFFLINE=1 /verify/venv/bin/python -m pytest packages/e2e/tests -q
PI_OFFLINE=1 /verify/venv/bin/python packages/e2e/tests/live_gate.py > /receipts/native-retry.json
mkdir -p /isolated/work
cd /isolated/work
mkdir -p .e2e
node --input-type=module <<'PROJECT'
import {writeFileSync} from "node:fs";
writeFileSync("test.feature","Feature: Test\nScenario: Before\nThen value is true\n");
writeFileSync("adapter.mjs",'process.argv[2]="unmet"; await import("file:///verify/packages/e2e/tests/run-fixture.mjs");');
writeFileSync(".e2e/runner.json",JSON.stringify({executable:process.execPath,args:["adapter.mjs"],adapterFiles:["adapter.mjs","/verify/packages/e2e/tests/run-fixture.mjs"]}));
PROJECT
PI_OFFLINE=1 PI_CODING_AGENT_DIR=/isolated/agent PI_E2E_AUTH=isolated-test-provider PI_E2E_CASE=retry pi --print --mode json --provider e2e-gate-scripted --model deterministic --no-skills --no-context-files --no-prompt-templates --extension /verify/packages/e2e/tests/live-fixture.ts --tools write,e2e_verify,e2e_gate_probe 'Update this feature and verify its e2e acceptance.' > /receipts/autoload.jsonl
node --input-type=module <<'ACCEPT'
import {readFileSync} from "node:fs";
const calls=readFileSync("/receipts/autoload.jsonl","utf8").split("\n").filter(line=>line.startsWith("{")).map(line=>JSON.parse(line)).filter(event=>event.type==="tool_execution_end"&&event.toolName==="e2e_verify");
const statuses=calls.map(call=>call.result.details.status);
if(JSON.stringify(statuses)!==JSON.stringify(["not_fulfilled","fulfilled","fulfilled","fulfilled"])||!calls.every(call=>call.result.details.verifiedRun)) throw Error("Packed autoload retry failed: "+JSON.stringify(statuses));
console.log(JSON.stringify({autoloadStatuses:statuses,verifiedRun:true}));
ACCEPT
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {createHash} from "node:crypto"; const settings=JSON.parse(readFileSync("/isolated/agent/settings.json")); if(settings.packages.length!==1) throw Error("Expected only the E2E package"); console.log(JSON.stringify({packages:settings.packages,e2eSha256:createHash("sha256").update(readFileSync(process.env.E2E_TARBALL)).digest("hex"),kitSha256:createHash("sha256").update(readFileSync(process.env.TASK_KIT_TARBALL)).digest("hex")}));'
SETUP
docker run -d --init --name "$container_name" -v "$receipt_dir:/receipts" -v "$repo_root/packages/e2e/tests:/e2e-tests:ro" -v "$repo_root/AGENTS.md:/root-agents:ro" -v "$repo_root/package.json:/root-manifest:ro" -v "$repo_root/pnpm-lock.yaml:/root-lockfile:ro" -v "$repo_root/tests/e2e/support:/shared-support:ro" -v "$repo_root/.e2e/runner.json:/runner-config:ro" -v "$repo_root/packages/goal/index.ts:/goal-entry:ro" -v "$repo_root/packages/goal/package.json:/goal-manifest:ro" -v "$repo_root/packages/goal/src:/goal-source:ro" -v "$repo_root/packages/goal/tests:/goal-tests:ro" -v "$repo_root/packages/tasks/src:/task-source:ro" -v "$repo_root/packages/tasks/tests:/task-tests:ro" -v "$repo_root/packages/goal/features:/goal-features:ro" -v "$repo_root/packages/tasks/features:/task-features:ro" -v "$repo_root/packages/e2e/package.json:/source-manifest:ro" -v "$repo_root/packages/e2e/AGENTS.md:/package-agents:ro" node:24-bookworm-slim sleep infinity > "$receipt_dir/container-id"
if docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'E2E_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -60 "$receipt_dir/verification.log"
  printf 'E2E_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
