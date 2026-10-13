/** Refuse network transport in the disposable offline Pi process. */
const fs = require("node:fs");
const deny = () => {
  fs.appendFileSync(process.env.PI_NATIVE_NETWORK_LOG, "network transport rejected\n");
  throw new Error("Network transport is forbidden in native offline acceptance");
};
globalThis.fetch = deny;
for (const moduleName of ["node:http", "node:https"]) {
  const module = require(moduleName);
  module.request = deny;
  module.get = deny;
}
const net = require("node:net");
net.connect = deny;
net.createConnection = deny;
net.Socket.prototype.connect = deny;
require("node:tls").connect = deny;
require("node:module").syncBuiltinESMExports();
