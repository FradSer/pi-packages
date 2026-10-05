/** Inspect the real settings/package resolver, before a keyed registry can hide
 * duplicate registrants. No package factories or extension paths are composed. */
import { DefaultResourceLoader, getAgentDir, SettingsManager } from "@earendil-works/pi-coding-agent";

const cwd = process.cwd();
const agentDir = getAgentDir();
const settingsManager = SettingsManager.create(cwd, agentDir, { projectTrusted: false });
const loader = new DefaultResourceLoader({
  cwd, agentDir, settingsManager,
  noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
});
await loader.reload();
const loaded = loader.getExtensions();
console.log(JSON.stringify({
  errors: loaded.errors,
  settingsErrors: settingsManager.drainErrors().map(({ path, error }) => ({ path, error: error.message })),
  extensions: loaded.extensions.map((extension) => ({
    path: extension.path,
    resolvedPath: extension.resolvedPath,
    sourceInfo: extension.sourceInfo,
    tools: [...extension.tools.values()].map(({ definition, sourceInfo }) => ({
      name: definition.name, parameters: definition.parameters, sourceInfo,
    })),
  })),
}));
