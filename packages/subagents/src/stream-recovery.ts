/** Pi 1.0 misses this transport diagnostic in its native retry classifier.
 * Classify only that message; Pi still owns budget, backoff, abort, and recovery.
 * Remove this contribution when the supported Pi cohort recognizes it natively.
 */
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const STREAM_RECOVERY_EXTENSION_PATH = fileURLToPath(import.meta.url);
const PREMATURE_CLOSE = /^(?:stream error:\s*)?stream disconnected before completion:\s*stream closed before response\.completed\s*$/i;
const WEBSOCKET_CLOSE = /^WebSocket stream closed before response\.completed\s*$/i;

export default function streamRecovery(pi: ExtensionAPI): void {
  pi.on("message_end", event => {
    const message = event.message;
    if (message.role !== "assistant" || message.stopReason !== "error" || !message.errorMessage
      || message.content.some(block => block.type === "toolCall")
      || (!PREMATURE_CLOSE.test(message.errorMessage) && !WEBSOCKET_CLOSE.test(message.errorMessage))) return;
    // Retain original output and diagnostic. This prefix lets Pi's normal
    // transport-error policy classify the response before its settle boundary.
    return { message: { ...message, errorMessage: `network error: ${message.errorMessage}` } };
  });
}
