import { z } from "zod";

// Imported by apps/web client code (chat tool cards): keep this module free of
// eve runtime, backend, and Node-only imports.

// Mirrors SqlResponse in apps/api/routers/market.py.
export const sqlResultSchema = z.object({
  columns: z.array(z.string()),
  rows: z.array(z.array(z.unknown())),
  row_count: z.number(),
  truncated: z.boolean(),
  error: z.string().nullable(),
  warning: z.string().nullable(),
  column_totals: z.record(z.string(), z.number()).nullable(),
  last_minus_first: z.record(z.string(), z.number()).nullable(),
});

export type SqlResult = z.infer<typeof sqlResultSchema>;

// Mirrors ProductResponse.
export const productMatchesSchema = z.object({
  matches: z.array(
    z.object({
      product: z.string(),
      product_en: z.string(),
      product_uz: z.string(),
      category: z.string(),
      units: z.array(z.string()),
      grades: z.array(z.string()),
      classes: z.array(z.string()),
      brands: z.array(z.string()),
      sizes: z.array(z.string()),
      product_types: z.array(z.string()),
      currencies: z.array(z.string()),
    }),
  ),
});

// Mirrors CompanyResponse.
export const companyMatchesSchema = z.object({
  matches: z.array(
    z.object({
      kind: z.string(),
      inn: z.string(),
      name: z.string(),
      region_uz: z.string(),
      role: z.string().nullable(),
      activity: z.string().nullable(),
      broker_code: z.string().nullable(),
    }),
  ),
  ambiguous: z.boolean(),
});
