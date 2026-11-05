import { defineTool } from "eve/tools";
import { z } from "zod";
import { backendRequest } from "../lib/backend";
import { sqlResultSchema } from "../lib/market";

export default defineTool({
  description:
    "Run one read-only PostgreSQL SELECT over the v_ views described in your instructions. Returns at most 200 rows, so aggregate in SQL and never add numbers up yourself. If `error` is set, fix the query and retry. If `warning` is set, act on it before you report the number. With several rows, `column_totals` holds the sum of each numeric column, and with two rows, `last_minus_first` holds their difference, so read totals and differences from there.",
  inputSchema: z.object({
    query: z.string().describe("A single SELECT statement."),
    purpose: z.string().describe("One short line, in the person's language, on what this computes."),
  }),
  outputSchema: sqlResultSchema,
  label: {
    start: ({ purpose }) => purpose,
    complete: ({ purpose }) => purpose,
  },
  async execute({ query }) {
    return sqlResultSchema.parse(await backendRequest("/tools/sql", { body: { query } }));
  },
});
