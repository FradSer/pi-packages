#!/bin/sh
# Registry-free Goal/kit tarballs, isolated Pi (latest by default), scripted native acceptance.
#
# The isolated baseline must be the current Pi. The version is resolved from the registry at
# run time, and every @earendil-works package in the isolated tree is pinned to it, so a
# transitive release cannot pull a second copy of the runtime in. Set PI_VERSION=x.y.z only to
# reproduce an older baseline deliberately.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
receipt_dir=$(mktemp -d "${TMPDIR:-/tmp}/goal-docker-XXXXXXXX")
container_name="goal-isolated-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"

pi_version=${PI_VERSION:-}
if [ -z "$pi_version" ]; then
  pi_version=$(pnpm view @earendil-works/pi-coding-agent dist-tags.latest 2>/dev/null | tr -d "[:space:]")
  if [ -z "$pi_version" ]; then
    printf "%s\n" "cannot resolve the latest Pi version from the registry; set PI_VERSION to pin one" >&2
    exit 1
  fi
fi
printf "%s\n" "$pi_version" > "$receipt_dir/pi-version.txt"
printf "isolated Pi baseline: %s\n" "$pi_version" >&2

pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/goal pack --pack-destination "$receipt_dir" > "$receipt_dir/goal-pack.log"
kit_tgz=$(basename "$(ls "$receipt_dir"/fradser-pi-kit-*.tgz | head -1)")
goal_tgz=$(basename "$(ls "$receipt_dir"/fradser-pi-goal-*.tgz | head -1)")

# Every @earendil-works package the Pi entry points depend on at this version.
pi_family=$(for pkg in pi-coding-agent pi-ai pi-tui; do
  pnpm view "@earendil-works/$pkg@$pi_version" dependencies --json 2>/dev/null
done | grep -o "\"@earendil-works/[a-z-]*\"" | tr -d "\"" | sed "s|^@earendil-works/||" | sort -u)

{
  printf "{\n  \"name\": \"isolated-goal-verification\",\n  \"private\": true,\n  \"type\": \"module\",\n"
  printf "  \"packageManager\": \"pnpm@11.21.0\",\n  \"dependencies\": {\n"
  for pkg in pi-coding-agent pi-ai pi-tui; do
    printf "    \"@earendil-works/%s\": \"%s\",\n" "$pkg" "$pi_version"
  done
  printf "    \"@fradser/pi-kit\": \"file:/receipts/%s\",\n" "$kit_tgz"
  printf "    \"@fradser/pi-goal\": \"file:/receipts/%s\",\n" "$goal_tgz"
  printf "    \"tsx\": \"^4.19.0\",\n    \"@babel/parser\": \"^7.29.9\",\n    \"typescript\": \"^5.9.0\",\n    \"@types/node\": \"^22.0.0\"\n  }\n}\n"
} > "$receipt_dir/isolated-package.json"


{
  printf "packages:\n  - .\noverrides:\n"
  printf "  \"@fradser/pi-kit\": file:/receipts/%s\n" "$kit_tgz"
  { for pkg in pi-coding-agent pi-ai pi-tui $pi_family; do printf "  \"@earendil-works/%s\": %s\n" "$pkg" "$pi_version"; done; } | sort -u
  printf "allowBuilds:\n  esbuild: true\n  \"@google/genai\": true\n  protobufjs: true\n"
} > "$receipt_dir/isolated-workspace.yaml"

cat > "$receipt_dir/setup.sh" <<'SETUP'
#!/bin/sh
set -eu
corepack enable
mkdir -p /isolated /verify/packages/goal/tests
cd /isolated
cp /receipts/isolated-package.json package.json
cp /receipts/isolated-workspace.yaml pnpm-workspace.yaml
pnpm install
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null
python3 -m venv /verify/venv
/verify/venv/bin/pip install -q pyte pytest
mkdir -p /verify/packages/goal
cp -R /goal-package/tests/. /verify/packages/goal/tests/
for entry in features package.json tsconfig.json tsconfig.tests.json AGENTS.md README.md TUI.zh-CN.md CONTEXT.md; do
  cp -R "/goal-package/$entry" /verify/packages/goal/
done
mkdir -p /verify/tests/e2e
cp -R /shared-support /verify/tests/e2e/support
ln -s /isolated/node_modules/@fradser/pi-goal/src /verify/packages/goal/src
ln -s /isolated/node_modules/@fradser/pi-goal/index.ts /verify/packages/goal/index.ts
ln -s /isolated/node_modules /verify/node_modules
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent
printf '%s\n' '{"packages":["/isolated/node_modules/@fradser/pi-goal"]}' > /isolated/agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list | tee /receipts/pi-list.txt
pi --version
# Only the Goal package may be loaded: kit is a library dependency, never an extension, and the
# isolated agent directory configures no other package.
grep -q "@fradser/pi-goal" /receipts/pi-list.txt || { echo "the Goal package is not loaded" >&2; exit 1; }
if grep -E "@fradser/pi-|/packages/(kit|tasks|utils|subagents|monitor|recap|keyboard|vision|btw|context)" /receipts/pi-list.txt | grep -qv "@fradser/pi-goal"; then
  echo "another package is loaded in the isolated environment" >&2; exit 1
fi
# The fixture registers its own provider; PI_OFFLINE keeps the acceptance from reaching a real
# model, and the isolated tree has no credentials to reach one with. The whole goal acceptance
# runs here: the package gate first, then every PTY probe the package documents.
cd /verify
echo "=== goal package gate: pytest packages/goal/tests ==="
PI_OFFLINE=1 GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python -m pytest packages/goal/tests/ -q
echo "=== goal PTY probes: completion (scripted and autoload), request row, revision ==="
PI_OFFLINE=1 GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_completion.py
PI_OFFLINE=1 PI_GOAL_AUTOLOAD=1 GOAL_INSTALLED_PATH=/isolated/node_modules/@fradser/pi-goal GOAL_CASES=empty,long GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_completion.py
PI_OFFLINE=1 GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_request_row.py
PI_OFFLINE=1 GOAL_VERIFY_ROOT=/verify /verify/venv/bin/python /verify/packages/goal/tests/goal_native_revision.py
node --input-type=module -e 'import {readFileSync,readdirSync} from "node:fs"; import {createHash} from "node:crypto"; const settings=JSON.parse(readFileSync("/isolated/agent/settings.json")); if(settings.packages.length!==1) throw Error("Expected only the Goal package"); const tarballs=Object.fromEntries(readdirSync("/receipts").filter(n=>/^fradser-pi-.*\.tgz$/.test(n)).map(n=>[n,createHash("sha256").update(readFileSync("/receipts/"+n)).digest("hex")])); console.log(JSON.stringify({piVersion:readFileSync("/receipts/pi-version.txt","utf8").trim(),packages:settings.packages,loadedPackages:readFileSync("/receipts/pi-list.txt","utf8").split("\n").map(l=>l.trim()).filter(Boolean),tarballs}));'
SETUP
docker run -d --name "$container_name" -v "$receipt_dir:/receipts" -v "$repo_root/packages/goal:/goal-package:ro" -v "$repo_root/tests/e2e/support:/shared-support:ro" node:24-bookworm-slim sleep infinity > "$receipt_dir/container-id"
if docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'GOAL_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -60 "$receipt_dir/verification.log"
  printf 'GOAL_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
