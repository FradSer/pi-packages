FROM node:22-bookworm@sha256:dd5847a04b0deee391fa145f1f4c6d214196668b6bcc7988ebed67249f226844
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /usr/local/bin/
ENV PNPM_HOME=/opt/pnpm
ENV COREPACK_HOME=/opt/corepack
ENV COREPACK_DEFAULT_TO_LATEST=0
ENV PATH=/opt/pnpm:/opt/experiment/node_modules/.bin:$PATH
RUN corepack enable && corepack prepare pnpm@11.21.0 --activate
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates git less && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/experiment
COPY packages/kit/package.json ./packages/kit/package.json
COPY packages/continual-learning/package.json ./packages/continual-learning/package.json
RUN node --input-type=module -e 'import fs from "node:fs";fs.writeFileSync("package.json",JSON.stringify({private:true,type:"module",packageManager:"pnpm@11.21.0",dependencies:{"@earendil-works/pi-coding-agent":"1.2.0","@earendil-works/pi-ai":"1.2.0","@earendil-works/pi-tui":"1.2.0",tsx:"4.19.0"}}));fs.writeFileSync("pnpm-workspace.yaml","packages:\n  - packages/*\noverrides:\n  \"@earendil-works/pi-coding-agent\": 1.2.0\n  \"@earendil-works/pi-ai\": 1.2.0\n  \"@earendil-works/pi-agent-core\": 1.2.0\n  \"@earendil-works/pi-codemode\": 1.2.0\n  \"@earendil-works/pi-mcp\": 1.2.0\n  \"@earendil-works/pi-telemetry\": 1.2.0\n  \"@earendil-works/pi-tui\": 1.2.0\nallowBuilds:\n  esbuild: true\n  \"@google/genai\": true\n  protobufjs: true\n");'
RUN pnpm install --no-frozen-lockfile
COPY packages/kit/index.ts packages/kit/README.md ./packages/kit/
COPY packages/kit/src ./packages/kit/src
COPY packages/continual-learning/index.ts packages/continual-learning/README.md ./packages/continual-learning/
COPY packages/continual-learning/extensions ./packages/continual-learning/extensions
COPY packages/continual-learning/prompts ./packages/continual-learning/prompts
COPY packages/continual-learning/scripts ./packages/continual-learning/scripts
RUN chmod -R a+rX /opt/corepack && mkdir -p /home/node/results /work /home/node/.cache /home/node/.local && chown -R node:node /home/node/results /work /home/node/.cache /home/node/.local
USER node
ENV HOME=/home/node
WORKDIR /work
CMD ["sleep", "infinity"]
