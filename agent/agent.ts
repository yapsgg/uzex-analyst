import { createOpenRouter } from "@openrouter/ai-sdk-provider";
import { defineAgent } from "eve";

const openrouter = createOpenRouter({ apiKey: process.env.OPENROUTER_API_KEY });

// A dated snapshot, so a silent model upgrade can't invalidate evaluation results.
// AGENT_MODEL lets the evaluation suite compare models without code changes.
export default defineAgent({
  // The agent only reads the market database through its own tools: no shell or web.
  defaultTools: false,
  limits: {
    sessionUsage: ({ window }) => window.inputTokens >= 300_000,
  },
  model: openrouter(process.env.AGENT_MODEL?.trim() || "deepseek/deepseek-v4-pro-0813"),
  // Eve only knows context windows for AI Gateway models, so declare it for OpenRouter.
  // 160k is the smallest window among the models we compare, and keeps compaction early.
  modelContextWindowTokens: 160_000,
});
