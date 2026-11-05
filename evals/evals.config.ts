import { defineEvalConfig } from "eve/evals";

export default defineEvalConfig({ maxConcurrency: 6, timeoutMs: 240_000 });
