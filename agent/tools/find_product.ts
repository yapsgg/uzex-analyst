import { defineTool } from "eve/tools";
import { z } from "zod";
import { backendRequest } from "../lib/backend";
import { productMatchesSchema } from "../lib/market";

export default defineTool({
  description:
    "Resolve what a person calls a product (any spelling, in Russian, Uzbek, or English) to its canonical `product` value, plus its units, currencies, grades, classes, brands, and sizes. Call it before filtering on a product or attribute.",
  inputSchema: z.object({ query: z.string().describe("The product as the person wrote it.") }),
  outputSchema: productMatchesSchema,
  label: {
    start: ({ query }) => `Looking up product "${query}"`,
    complete: ({ query }, output) => `Found ${output.matches.length} for "${query}"`,
  },
  async execute({ query }) {
    return productMatchesSchema.parse(
      await backendRequest("/tools/find-product", { body: { query } }),
    );
  },
});
