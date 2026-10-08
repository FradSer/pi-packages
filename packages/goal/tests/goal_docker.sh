#!/bin/sh
# Registry-free Goal/kit tarballs, isolated Pi 1.0.4, scripted native acceptance.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
receipt_dir=$(mktemp -d "${TMPDIR:-/tmp}/goal-docker-XXXXXXXX")
container_name="goal-isolated-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"
pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/goal pack --pack-destination "$receipt_dir" > "$receipt_dir/goal-pack.log"
cat > "$receipt_dir/setup.sh" <<'SETUP'
#!/bin/sh
set -eu
corepack enable
mkdir -p /isolated /verify/packages/goal/tests
cd /isolated
cat > package.json <<'JSON'
{"name":"isolated-goal-verification","private":true,"type":"module","packageManager":"pnpm@11.21.0","dependencies":{"@earendil-works/pi-coding-agent":"1.0.4","@earendil-works/pi-ai":"1.0.4","@earendil-works/pi-tui":"1.0.4","@fradser/pi-kit":"file:/receipts/fradser-pi-kit-0.5.1.tgz","@fradser/pi-goal":"file:/receipts/fradser-pi-goal-0.1.0.tgz","tsx":"^4.19.0","@babel/parser":"^7.29.9"}}
JSON
cat > pnpm-workspace.yaml <<'YAML'
packages:
  - '.'
overrides:
  '@fradser/pi-kit': file:/receipts/fradser-pi-kit-0.5.1.tgz
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
pnpm install
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null
python3 -m venv /verify/venv
/verify/venv/bin/pip install -q pyte
cp -R /goal-tests/. /verify/packages/goal/tests/
mkdir -p /verify/tests/e2e
cp -R /shared-support /verify/tests/e2e/support
ln -s /isolated/node_modules/@fradser/pi-goal/src /verify/packages/goal/src
ln -s /isolated/node_modules/@fradser/pi-goal/index.ts /verify/packages/goal/index.ts
ln -s /isolated/node_modules /verify/node_modules
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent
printf '%s\n' '{"packages":["/isolated/node_modules/@fradser/pi-goal"]}' > /isolated/agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list
pi --version
GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_completion.py
PI_GOAL_AUTOLOAD=1 GOAL_INSTALLED_PATH=/isolated/node_modules/@fradser/pi-goal GOAL_CASES=empty,long GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_completion.py
cd /verify
node --import tsx packages/goal/tests/goal_simplified.mts
node --import tsx packages/goal/tests/goal_store.mts
node --import tsx packages/goal/tests/goal_scheduling.mts
node --import tsx packages/goal/tests/goal_session.mts
node --input-type=module -e 'import {readFileSync} from "node:fs"; import {createHash} from "node:crypto"; const settings=JSON.parse(readFileSync("/isolated/agent/settings.json")); if(settings.packages.length!==1) throw Error("Expected only the Goal package"); console.log(JSON.stringify({packages:settings.packages,goalSha256:createHash("sha256").update(readFileSync("/receipts/fradser-pi-goal-0.1.0.tgz")).digest("hex"),kitSha256:createHash("sha256").update(readFileSync("/receipts/fradser-pi-kit-0.5.1.tgz")).digest("hex")}));'
SETUP
docker run -d --name "$container_name" -v "$receipt_dir:/receipts" -v "$repo_root/packages/goal/tests:/goal-tests:ro" -v "$repo_root/tests/e2e/support:/shared-support:ro" node:24-bookworm-slim sleep infinity > "$receipt_dir/container-id"
if docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'GOAL_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -60 "$receipt_dir/verification.log"
  printf 'GOAL_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
