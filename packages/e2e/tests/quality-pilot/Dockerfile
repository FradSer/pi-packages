FROM node:24-bookworm-slim
WORKDIR /opt/pilot-runtime
RUN npm init -y && npm install --save-exact @earendil-works/pi-coding-agent@1.0.4
COPY packages/e2e/ node_modules/@fradser/pi-e2e/
COPY packages/kit/ node_modules/@fradser/pi-kit/
RUN node -e "const fs=require('fs');const p='node_modules/@fradser/pi-e2e/package.json';const x=JSON.parse(fs.readFileSync(p));x.dependencies['@fradser/pi-kit']='0.5.1';fs.writeFileSync(p,JSON.stringify(x));"
ENV PATH="/opt/pilot-runtime/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"
WORKDIR /workspace
CMD ["tail", "-f", "/dev/null"]
