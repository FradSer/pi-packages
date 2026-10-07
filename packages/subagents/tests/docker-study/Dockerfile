FROM node:24-bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
RUN corepack enable && corepack prepare pnpm@11.21.0 --activate
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates git && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/study
COPY package.json pnpm-workspace.yaml ./
COPY packages/kit/package.json ./packages/kit/package.json
COPY packages/subagents/package.json ./packages/subagents/package.json
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm add -Dw --save-exact @earendil-works/pi-coding-agent@1.0.4 @earendil-works/pi-tui@1.0.4 tsx@4.23.12 typebox@1.3.12
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --no-frozen-lockfile
ENV UV_PYTHON_INSTALL_DIR=/opt/python
RUN uv venv --python 3.13 /opt/venv && uv pip install --python /opt/venv/bin/python pytest
COPY packages ./packages
ENV PATH=/opt/study/node_modules/.bin:/opt/venv/bin:$PATH
RUN mkdir /work /results /agent && chown -R node:node /work /results /agent
USER node
WORKDIR /work
CMD ["sleep", "infinity"]
