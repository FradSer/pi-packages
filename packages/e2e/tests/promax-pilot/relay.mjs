import http from "node:http";

// A task container has only an internal Docker network. This relay exposes
// exactly the configured model transport, not an arbitrary internet proxy.
http.createServer((request, response) => {
  if (request.method !== "POST" || !["/v1/chat/completions", "/v1/responses"].includes(request.url)) {
    response.writeHead(403); response.end(); return;
  }
  const upstream = http.request({ hostname: "host.docker.internal", port: process.env.PILOT_PROXY_PORT,
    path: request.url, method: "POST", headers: request.headers }, (incoming) => {
    response.writeHead(incoming.statusCode, incoming.headers);
    incoming.pipe(response);
  });
  upstream.on("error", () => { response.writeHead(502); response.end("Model transport unavailable"); });
  request.pipe(upstream);
}).listen(8080, "0.0.0.0");
