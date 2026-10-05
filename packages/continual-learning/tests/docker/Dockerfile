FROM node:22-bookworm@sha256:dd5847a04b0deee391fa145f1f4c6d214196668b6bcc7988ebed67249f226844
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /usr/local/bin/
ENV PNPM_HOME=/opt/pnpm
ENV COREPACK_HOME=/opt/corepack
ENV COREPACK_DEFAULT_TO_LATEST=0
ENV PATH=/opt/pnpm:/opt/experiment/node_modules/.bin:$PATH
RUN corepack enable && corepack prepare pnpm@11.21.0 --activate
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates git less && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/experiment
COPY package.json pnpm-workspace.yaml ./
COPY packages/kit/package.json ./packages/kit/package.json
COPY packages/continual-learning/package.json ./packages/continual-learning/package.json
RUN pnpm install --no-frozen-lockfile
COPY packages/kit ./packages/kit
COPY packages/continual-learning ./packages/continual-learning
RUN chmod -R a+rX /opt/corepack
RUN mkdir /work && chown node:node /work
USER node
ENV HOME=/home/node
WORKDIR /work
CMD ["sleep", "infinity"]
