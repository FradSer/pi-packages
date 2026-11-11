#!/usr/bin/env bash
# changesets/action runs this to produce the version PR, then refreshes the
# lockfile the packer reads.
#
# When it fails, the runner reports only "bun failed with exit code 1", which
# cannot be read without workflow-log access. Report the tree the action left
# checked out and the CLI's own words as annotations instead.
set -uo pipefail

head_sha=$(git rev-parse HEAD)
head_name=$(git rev-parse --abbrev-ref HEAD)
changeset_files=$(find .changeset -maxdepth 1 -name '*.md' ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')
echo "tree: sha=${head_sha} ref=${head_name} changesets=${changeset_files} cwd=$(pwd)"

output=$(bun x changeset version 2>&1)
code=$?
echo "${output}"

if [ "${code}" -ne 0 ]; then
  printf '::error::changeset version exited %s: %s changeset files, sha=%s ref=%s\n' \
    "${code}" "${changeset_files}" "${head_sha}" "${head_name}"
  printf '::error::%s\n' "$(printf '%s' "${output}" | tail -c 700 | tr '\n' ' ')"
  exit "${code}"
fi

bun install
