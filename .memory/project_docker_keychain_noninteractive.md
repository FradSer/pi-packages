---
name: "project_docker_keychain_noninteractive.md"
description: "Non-interactive docker on this macOS host fails credential lookup (osxkeychain 'keychain cannot be accessed', exit 125) before pulling; running docker with a HOME without docker config pulled node:22-bookworm and ran the Linux CI reproduction."
type: project
---
Observed: `docker run` for an image missing locally printed `Unable to find image 'node:22-bookworm' locally`, then `docker: error getting credentials - err: exit status 1, out: keychain cannot be accessed because the current session does not allow user interaction...`, and the script exited `CI_REPRO_EXIT=125`; a direct `docker pull -q node:22-bookworm` failed with the same credential error.

The host's `~/.docker/config.json` declares `"credsStore": "osxkeychain"` and `"currentContext": "orbstack"`.

How to apply: run docker with `HOME` pointed at a directory that has no docker config; `HOME=/tmp/pp-scratch/fakehome docker pull -q node:22-bookworm` printed `docker.io/library/node:22-bookworm`, and `HOME=/tmp/pp-scratch/fakehome docker run --rm ...` then produced bun `1.4.4`, node `v22.23.4` and `INSTALL OK`.

The evidence covers only a missing image pulled in a non-interactive session; other docker operations and other credential-helper configurations were not tested.