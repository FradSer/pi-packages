#!/bin/sh
# Packed Tasks/kit tarballs, isolated Pi 1.0.4, scripted native acceptance.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
receipt_dir=$(mktemp -d "${TMPDIR:-/tmp}/tasks-docker-XXXXXXXX")
container_name="tasks-isolated-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"
pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/tasks pack --pack-destination "$receipt_dir" > "$receipt_dir/tasks-pack.log"
cat > "$receipt_dir/setup.sh" <<'SETUP'
#!/bin/sh
set -eu
corepack enable
mkdir -p /isolated /verify/packages/tasks/tests
cd /isolated
set -- /receipts/fradser-pi-kit-*.tgz
export TASK_KIT_TARBALL="$1"
set -- /receipts/fradser-pi-tasks-*.tgz
export TASKS_TARBALL="$1"
node --input-type=module <<'JSON'
import { writeFileSync } from "node:fs";
const kit = `file:${process.env.TASK_KIT_TARBALL}`;
writeFileSync("package.json", JSON.stringify({
  name: "isolated-tasks-verification", private: true, type: "module", packageManager: "pnpm@11.21.0",
  dependencies: {
    "@earendil-works/pi-coding-agent": "1.0.4", "@earendil-works/pi-ai": "1.0.4", "@earendil-works/pi-tui": "1.0.4",
    "@fradser/pi-kit": kit, "@fradser/pi-tasks": `file:${process.env.TASKS_TARBALL}`,
    tsx: "^4.19.0", typebox: "^1.3.12",
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
cp -R /tasks-tests/. /verify/packages/tasks/tests/
cp /root-agents /verify/AGENTS.md
mkdir -p /verify/packages/subagents/src
cp /registry-reference /verify/packages/subagents/src/participant-registry.ts
ln -s /isolated/node_modules/@fradser/pi-tasks/src /verify/packages/tasks/src
ln -s /isolated/node_modules/@fradser/pi-tasks/index.ts /verify/packages/tasks/index.ts
ln -s /isolated/node_modules/@fradser/pi-tasks/TUI.zh-CN.md /verify/packages/tasks/TUI.zh-CN.md
ln -s /isolated/node_modules/@fradser/pi-tasks/README.md /verify/packages/tasks/README.md
ln -s /isolated/node_modules/@fradser/pi-tasks/package.json /verify/packages/tasks/package.json
mkdir -p /verify/packages/kit
ln -s /isolated/node_modules/@fradser/pi-kit/src /verify/packages/kit/src
ln -s /isolated/node_modules/@fradser/pi-kit/index.ts /verify/packages/kit/index.ts
ln -s /isolated/node_modules /verify/node_modules
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent
printf '%s\n' '{"packages":["/isolated/node_modules/@fradser/pi-tasks"]}' > /isolated/agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list
pi --version
export NODE_OPTIONS=--import=/isolated/node_modules/tsx/dist/loader.mjs
cd /verify
PI_OFFLINE=1 /verify/venv/bin/python -m pytest packages/tasks/tests -q
PI_OFFLINE=1 /verify/venv/bin/python packages/tasks/tests/task_native_frames.py --output /receipts/native-frames
mkdir -p /isolated/work
cd /isolated/work
PI_OFFLINE=1 PI_CODING_AGENT_DIR=/isolated/agent PI_TASK_TEST_MODE=recover PI_TASK_TEST_OUTPUT=/receipts/autoload.jsonl PI_TASK_TEST_WORK_DIR=/isolated/work pi --print --provider tasks-stop-test --model scripted --no-skills --no-context-files --no-prompt-templates --extension /verify/packages/tasks/tests/task-stop-live-fixture.ts --tools create_task,get_task,list_tasks,update_task,read,write 'Complete the two tasks in dependency order.'
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {createHash} from "node:crypto"; const settings=JSON.parse(readFileSync("/isolated/agent/settings.json")); if(settings.packages.length!==1) throw Error("Expected only the Tasks package"); console.log(JSON.stringify({packages:settings.packages,tasksSha256:createHash("sha256").update(readFileSync(process.env.TASKS_TARBALL)).digest("hex"),kitSha256:createHash("sha256").update(readFileSync(process.env.TASK_KIT_TARBALL)).digest("hex")}));'
SETUP
docker run -d --name "$container_name" -v "$receipt_dir:/receipts" -v "$repo_root/packages/tasks/tests:/tasks-tests:ro" -v "$repo_root/AGENTS.md:/root-agents:ro" -v "$repo_root/packages/subagents/src/participant-registry.ts:/registry-reference:ro" node:24-bookworm-slim sleep infinity > "$receipt_dir/container-id"
if docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'TASKS_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -60 "$receipt_dir/verification.log"
  printf 'TASKS_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
