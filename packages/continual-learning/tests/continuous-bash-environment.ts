/** Study-only native Bash definition. Parent learning authentication stays private. */
import {createBashToolDefinition, type ExtensionAPI} from "@earendil-works/pi-coding-agent";

export default function studyBashEnvironment(pi: ExtensionAPI): void {
  pi.registerTool(createBashToolDefinition(process.cwd(), {
    spawnHook: context => {
      const env = {...context.env};
      delete env.TYPESAFE_API_KEY;
      return {...context, env};
    },
  }));
}
