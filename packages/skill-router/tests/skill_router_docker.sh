#!/bin/sh
# Registry-free skill-router/kit tarballs, isolated Pi, scripted end-to-end acceptance.
#
# The isolated baseline is pinned rather than resolved from the registry: this
# package depends on Pi's tool exposure rules (a `codemode` tool is callable from a
# script, never declarable) and on the codemode sandbox, so the acceptance runs
# against the version the change was verified with. Set PI_VERSION=x.y.z to check
# another one deliberately.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
receipt_dir=$(mktemp -d "${TMPDIR:-/tmp}/skill-router-docker-XXXXXXXX")
container_name="skill-router-isolated-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"

pi_version=${PI_VERSION:-1.3.0}
printf "%s\n" "$pi_version" > "$receipt_dir/pi-version.txt"
printf "isolated Pi baseline: %s\n" "$pi_version" >&2

pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/skill-router pack --pack-destination "$receipt_dir" > "$receipt_dir/skill-router-pack.log"
kit_tgz=$(basename "$(ls "$receipt_dir"/fradser-pi-kit-*.tgz | head -1)")
router_tgz=$(basename "$(ls "$receipt_dir"/pi-skill-router-*.tgz | head -1)")

# Every @earendil-works package the Pi entry points depend on at this version, so a
# transitive release cannot pull a second copy of the runtime into the tree.
pi_family=$(for pkg in pi-coding-agent pi-ai pi-tui; do
  pnpm view "@earendil-works/$pkg@$pi_version" dependencies --json 2>/dev/null
done | grep -o "\"@earendil-works/[a-z-]*\"" | tr -d "\"" | sed "s|^@earendil-works/||" | sort -u)

{
  printf "{\n  \"name\": \"isolated-skill-router-verification\",\n  \"private\": true,\n  \"type\": \"module\",\n"
  printf "  \"packageManager\": \"pnpm@11.21.0\",\n  \"dependencies\": {\n"
  for pkg in pi-coding-agent pi-ai pi-tui; do
    printf "    \"@earendil-works/%s\": \"%s\",\n" "$pkg" "$pi_version"
  done
  printf "    \"@fradser/pi-kit\": \"file:/receipts/%s\",\n" "$kit_tgz"
  printf "    \"pi-skill-router\": \"file:/receipts/%s\",\n" "$router_tgz"
  printf "    \"tsx\": \"^4.19.0\",\n    \"typebox\": \"*\"\n  }\n}\n"
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
mkdir -p /isolated /verify/packages/skill-router/tests
cd /isolated
cp /receipts/isolated-package.json package.json
cp /receipts/isolated-workspace.yaml pnpm-workspace.yaml
pnpm install
apt-get update -qq
apt-get install -y -qq python3 python3-venv git curl unzip >/dev/null
# The package suite and `pnpm check` require Bun (CI pins 1.4.1): one registry test
# reads the module through `bun -e`, so the image provides the declared runtime
# instead of skipping that test. The official installer is pinned; npm's bun
# postinstall fetches the same binary through undici, which timed out here.
curl -fsSL --retry 3 --retry-delay 2 --max-time 300 https://bun.sh/install -o /tmp/bun-install.sh
BUN_INSTALL=/usr/local bash /tmp/bun-install.sh bun-v1.4.1 >/dev/null
bun --version | tee /receipts/bun-version.txt
python3 -m venv /verify/venv
/verify/venv/bin/pip install -q pytest
cp -R /skill-router-package/tests/. /verify/packages/skill-router/tests/
for entry in features package.json AGENTS.md README.md GLOSSARY.md; do
  cp -R "/skill-router-package/$entry" /verify/packages/skill-router/
done
ln -s /isolated/node_modules/pi-skill-router/src /verify/packages/skill-router/src
ln -s /isolated/node_modules/pi-skill-router/index.ts /verify/packages/skill-router/index.ts
ln -s /isolated/node_modules /verify/node_modules
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent /isolated/e2e-agent
# Two isolated agent directories, each with one purpose. `/isolated/agent` proves the
# packed package installs and loads; `/isolated/e2e-agent` runs the E2E assemblies,
# where the fixture owns the extension wiring so the order in which the routing
# section is read cannot race a settings-loaded copy of the same extension. The E2E
# directory declares codemode without an allowlist and with no inline tool list, so
# only searchTools can find a skill tool.
printf '%s\n' '{"packages":["/isolated/node_modules/pi-skill-router"]}' > /isolated/agent/settings.json
printf '%s\n' '{"defaultTools":["+codemode"],"codemode":{"inlineBudget":0}}' > /isolated/e2e-agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list | tee /receipts/pi-list.txt
pi --version | tee /receipts/pi-version-actual.txt
grep -q "pi-skill-router" /receipts/pi-list.txt || { echo "the skill-router package is not loaded" >&2; exit 1; }
if grep -E "pi-(skill-router|kit|tasks|goal|utils|subagents|monitor|recap|keyboard|vision|btw|context)" /receipts/pi-list.txt | grep -qv "pi-skill-router"; then
  echo "another package is loaded in the isolated environment" >&2; exit 1
fi

cd /verify
# Warm corepack before the gate: one package test shells out to `pnpm exec tsx`
# under a 20-second budget, and the first corepack download in a fresh image is
# slower than that budget. The warm-up uses the same working directory, because that
# is what decides which pnpm version corepack resolves.
corepack pnpm --version >/dev/null 2>&1 || pnpm --version >/dev/null
pnpm exec tsx --version >/dev/null 2>&1 || true
echo "=== skill-router package gate: pytest packages/skill-router/tests ==="
PI_OFFLINE=1 /verify/venv/bin/python -m pytest packages/skill-router/tests/ -q

echo "=== install a collection through the router (real clone, materialization, registry) ==="
mkdir -p /isolated/work /isolated/upstream/skills/seo-audit /isolated/upstream/skills/release-notes
cat > /isolated/upstream/skills/seo-audit/SKILL.md <<'SKILL'
---
name: seo-audit
description: When the user wants to audit, review, or diagnose SEO issues.
---

# SEO audit

WORKFLOW TOKEN: UNIQUE-TOKEN-SEO-7742
SKILL
cat > /isolated/upstream/skills/release-notes/SKILL.md <<'SKILL'
---
name: release-notes
description: Write release notes and changelog entries from merged changes.
---

# Release notes

Group merged changes by user impact and name the migration step.
SKILL
cd /isolated/upstream
git init -q -b main
git add -A
git -c user.email=test@test -c user.name=test commit -qm init
cd /verify
PI_CODING_AGENT_DIR=/isolated/e2e-agent npx tsx packages/skill-router/tests/router_harness.ts add /isolated/upstream --description "Search engine and release communication workflows."
test -f /isolated/e2e-agent/skill-router/collections.json
test -f /isolated/e2e-agent/skill-router/exposed/collections/upstream/leaves/seo-audit/SKILL.md

echo "=== scripted E2E: codemode searches the tools and calls the matched skill ==="
PI_OFFLINE=1 PI_CODING_AGENT_DIR=/isolated/e2e-agent /verify/venv/bin/python packages/skill-router/tests/skill_router_e2e.py \
  --mode codemode --agent-dir /isolated/e2e-agent --cwd /isolated/work \
  --fixture /verify/packages/skill-router/tests/skill_router_e2e_fixture.ts \
  --tool skill_router__upstream__seo_audit

echo "=== scripted E2E: the fallback assembly keeps the routing suggestion ==="
PI_OFFLINE=1 PI_CODING_AGENT_DIR=/isolated/e2e-agent /verify/venv/bin/python packages/skill-router/tests/skill_router_e2e.py \
  --mode fallback --agent-dir /isolated/e2e-agent --cwd /isolated/work \
  --fixture /verify/packages/skill-router/tests/skill_router_e2e_fixture.ts \
  --tool skill_router__upstream__seo_audit

node --input-type=module -e 'import {readFileSync,readdirSync,existsSync} from "node:fs"; import {createHash} from "node:crypto"; const settings=JSON.parse(readFileSync("/isolated/agent/settings.json")); if(settings.packages.length!==1) throw Error("Expected only the skill-router package"); const registry=JSON.parse(readFileSync("/isolated/e2e-agent/skill-router/collections.json")); if(registry.collections.length!==1) throw Error("Expected one installed collection"); const e2eSettings=JSON.parse(readFileSync("/isolated/e2e-agent/settings.json")); if(e2eSettings.packages) throw Error("The E2E agent directory must not install the package"); const tarballs=Object.fromEntries(readdirSync("/receipts").filter(n=>/\.tgz$/.test(n)).map(n=>[n,createHash("sha256").update(readFileSync("/receipts/"+n)).digest("hex")])); console.log(JSON.stringify({piVersion:readFileSync("/receipts/pi-version-actual.txt","utf8").trim(),packages:settings.packages,loadedPackages:readFileSync("/receipts/pi-list.txt","utf8").split("\n").map(l=>l.trim()).filter(Boolean),collections:registry.collections.map(c=>({id:c.id,gateway:c.gateway,skills:c.routes.map(r=>r.skill),exposed:existsSync(`/isolated/e2e-agent/skill-router/exposed/collections/${c.id}/gateway/SKILL.md`)})),tarballs}));'
SETUP
docker run -d --name "$container_name" -v "$receipt_dir:/receipts" -v "$repo_root/packages/skill-router:/skill-router-package:ro" node:24-bookworm-slim sleep infinity > "$receipt_dir/container-id"
if docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'SKILL_ROUTER_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -80 "$receipt_dir/verification.log"
  printf 'SKILL_ROUTER_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi