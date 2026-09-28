/**
 * Reads back the tool surface a *configured install* produced.
 *
 * The E2E suites compose an install by hand, which proves each combination works
 * but says nothing about whether a real Pi finds the packages. This one asks the
 * host what it actually built, through the extension API, and writes the list out
 * for the suite to read.
 *
 * It registers no tool of its own, so the surface it reports is exactly what the
 * configured packages contributed.
 */

import * as fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { installScriptedProvider } from "../../../../tests/e2e/support/scripted.ts";

export default function installProbe(pi: ExtensionAPI): void {
  installScriptedProvider(pi, {
    provider: "install-probe",
    probe: "install_surface_probe",
    // One turn, so the probe runs once and reads the finished surface. The report
    // afterwards costs nothing and keeps the run from failing on an empty script.
    turns: [{ tool: "install_surface_probe", args: {} }],
    dumpPath: process.env.PI_INSTALL_PROBE,
  });
}
