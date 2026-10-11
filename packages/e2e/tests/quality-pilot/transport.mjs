// Transparent URL routing only. Preserve the production request body/model.
// Pi preserves deliberate fetch overrides made after its dispatcher module loads.
await import('/opt/pilot-runtime/node_modules/@earendil-works/pi-coding-agent/dist/core/http-dispatcher.js');
const originalFetch = globalThis.fetch;
globalThis.fetch = (input, options) => {
  if (String(input) === "https://api.typesafe.ai/v1/systemone") {
    return originalFetch("http://model-proxy:8080/jev/v1/systemone", options).catch(error => { console.error("Jev transport cause", error.cause?.code ?? error.message); throw error; });
  }
  return originalFetch(input, options);
};
