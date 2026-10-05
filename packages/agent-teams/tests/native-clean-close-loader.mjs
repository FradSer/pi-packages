import { fileURLToPath } from "node:url";

// NODE_OPTIONS loads this fixture before the isolated native child starts Pi.
// The parent script receives no added extension.
if (process.argv[1]?.endsWith("/cli.js")) {
  process.argv.push("--extension", fileURLToPath(new URL("./clean-close-native-fixture.ts", import.meta.url)));
}
