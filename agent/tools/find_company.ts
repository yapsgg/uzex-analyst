import { defineTool } from "eve/tools";
import { z } from "zod";
import { backendRequest } from "../lib/backend";
import { companyMatchesSchema } from "../lib/market";

export default defineTool({
  description:
    "Resolve a company or broker from a name in Latin or Cyrillic, a 9-digit INN, or a BK code. Names are not unique, so filter later queries by the returned `inn` or `broker_code`, never by name.",
  inputSchema: z.object({ query: z.string().describe("Name, INN, or broker code.") }),
  outputSchema: companyMatchesSchema,
  label: {
    start: ({ query }) => `Looking up "${query}"`,
    complete: ({ query }, output) => `Found ${output.matches.length} for "${query}"`,
  },
  async execute({ query }) {
    return companyMatchesSchema.parse(
      await backendRequest("/tools/find-company", { body: { query } }),
    );
  },
});
