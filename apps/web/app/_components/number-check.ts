import type { EveMessage } from "eve/react";

import { unsupportedNumbers } from "../../../../agent/lib/numbers";

/**
 * Numbers in an assistant message that no query returned. Sources are the tool results and the
 * person's own messages, up to and including this message.
 *
 * @param messages - The conversation so far.
 * @param index - The position of the message to check.
 * @returns The numbers as written in the reply; empty when every number traces back.
 */
export function unverifiedNumbers(messages: readonly EveMessage[], index: number): string[] {
  const message = messages[index];
  if (message === undefined || message.role !== "assistant") {
    return [];
  }
  const sources: unknown[] = [];
  for (const earlier of messages.slice(0, index + 1)) {
    for (const part of earlier.parts) {
      if (part.type === "text" && earlier.role === "user") {
        sources.push(part.text);
      } else if (part.type !== "text" && part.type !== "reasoning" && "output" in part) {
        sources.push(part.output);
      }
    }
  }
  const reply = message.parts.flatMap((part) => (part.type === "text" ? [part.text] : [])).join("\n");
  return unsupportedNumbers(reply, sources);
}
