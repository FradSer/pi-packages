#!/bin/sh
# Packed utils/kit tarballs, isolated Pi, real git worktree creation on Linux.
#
# Two layers of evidence, both through the packed package:
#   1. worktree_creation_cases.py drives pi --print so the real bash tool runs
#      each redirected command and the disk result is read back.
#   2. worktree_notice_pty.py drives the real interactive CLI through a PTY,
#      because print mode drops ui.notify.
set -eu
# The base image decides the container git version. Debian bookworm ships git
# 2.39, which has no 'git worktree add --orphan', so that case is skipped there;
# UTILS_DOCKER_BASE_IMAGE=node:24-trixie-slim exercises it on git 2.47.
base_image=$(printenv UTILS_DOCKER_BASE_IMAGE || true)
[ -n "$base_image" ] || base_image=node:24-bookworm-slim
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
# An unset TMPDIR must not stop the harness before its first tool call: this
# script runs under 'set -u', and Linux CI hosts usually export no TMPDIR.
tmp_parent=${TMPDIR:-/tmp}
receipt_dir=$(mktemp -d "$tmp_parent/utils-docker-XXXXXXXX")
container_name="utils-worktree-$$"
cleanup() { docker rm -f "$container_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
cd "$repo_root"
pnpm --dir packages/kit pack --pack-destination "$receipt_dir" > "$receipt_dir/kit-pack.log"
pnpm --dir packages/utils pack --pack-destination "$receipt_dir" > "$receipt_dir/utils-pack.log"
cat > "$receipt_dir/setup.sh" <<'SETUP'
#!/bin/sh
set -eu
corepack enable
mkdir -p /isolated /verify
cd /isolated
set -- /receipts/fradser-pi-kit-*.tgz
export WORKTREE_KIT_TARBALL="$1"
set -- /receipts/fradser-pi-utils-*.tgz
export WORKTREE_UTILS_TARBALL="$1"
node --input-type=module <<'JSON'
import { writeFileSync } from "node:fs";
const kit = 'file:' + process.env.WORKTREE_KIT_TARBALL;
writeFileSync("package.json", JSON.stringify({
  name: "isolated-utils-verification", private: true, type: "module", packageManager: "pnpm@11.21.0",
  dependencies: {
    "@earendil-works/pi-coding-agent": "1.2.0", "@earendil-works/pi-ai": "1.2.0", "@earendil-works/pi-tui": "1.2.0",
    "@fradser/pi-kit": kit, "@fradser/pi-utils": 'file:' + process.env.WORKTREE_UTILS_TARBALL,
    tsx: "^4.19.0", typebox: "^1.3.12",
  },
}, null, 2) + "\n");
JSON
cat > pnpm-workspace.yaml <<'YAML'
packages:
  - '.'
overrides:
  '@earendil-works/chord': 1.2.0
  '@earendil-works/pi-agent-core': 1.2.0
  '@earendil-works/pi-ai': 1.2.0
  '@earendil-works/pi-codemode': 1.2.0
  '@earendil-works/pi-mcp': 1.2.0
  '@earendil-works/pi-tui': 1.2.0
allowBuilds:
  esbuild: true
  '@google/genai': true
  protobufjs: true
YAML
node --input-type=module <<'OVERRIDE'
import { readFileSync, writeFileSync } from "node:fs";
const yaml = readFileSync("pnpm-workspace.yaml", "utf8");
writeFileSync("pnpm-workspace.yaml", yaml.replace("overrides:\n",
  "overrides:\n  '@fradser/pi-kit': " + JSON.stringify("file:" + process.env.WORKTREE_KIT_TARBALL) + "\n"));
OVERRIDE
pnpm install
apt-get update -qq
apt-get install -y -qq git python3 python3-venv >/dev/null
python3 -m venv /verify/venv
/verify/venv/bin/pip install -q pyte
ln -s /isolated/node_modules/.bin/pi /usr/local/bin/pi
mkdir -p /isolated/agent /isolated/home
printf '%s\n' '{"packages":["/isolated/node_modules/@fradser/pi-utils"]}' > /isolated/agent/settings.json
PI_CODING_AGENT_DIR=/isolated/agent pi list
pi --version
git --version
SETUP
cat > "$receipt_dir/run-cases.sh" <<'CASES'
#!/bin/sh
# Both layers run even when one fails, and their work directories live in the
# receipt volume so a failed run keeps its per-case Pi transcripts.
set -u
export PI_WORKTREE_FIXTURE=/utils-tests/worktree_bash_fixture.ts
export PI_WORKTREE_AGENT_DIR=/isolated/agent
export PI_WORKTREE_HOME=/isolated/home
status=0
python3 /utils-tests/worktree_creation_cases.py --output /receipts/creation --work /receipts/work || status=1
/verify/venv/bin/python /utils-tests/worktree_notice_pty.py --output /receipts/notices --work /receipts/notice-work || status=1
for file in /receipts/creation/*/pi.stderr /receipts/work/*/pi.stderr; do
  [ -s "$file" ] || continue
  echo "--- $file"
  head -20 "$file"
done
exit $status
CASES
printf '%s\n' "$base_image" > "$receipt_dir/base-image.txt"
docker run -d --name "$container_name" \
  -v "$receipt_dir:/receipts" \
  -v "$repo_root/packages/utils/tests:/utils-tests:ro" \
  "$base_image" sleep infinity > "$receipt_dir/container-id"
if ! docker exec "$container_name" sh /receipts/setup.sh > "$receipt_dir/setup.log" 2>&1; then
  # A silent exit here hides the cause: the container install is the step most
  # likely to fail on a transient network error.
  tail -40 "$receipt_dir/setup.log"
  printf 'UTILS_DOCKER_SETUP_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
if docker exec "$container_name" sh /receipts/run-cases.sh > "$receipt_dir/verification.log" 2>&1; then
  printf 'UTILS_DOCKER_OK %s\n' "$receipt_dir"
else
  tail -80 "$receipt_dir/verification.log"
  printf 'UTILS_DOCKER_FAILED %s\n' "$receipt_dir" >&2
  exit 1
fi
