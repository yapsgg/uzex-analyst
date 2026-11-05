# Exchange Analyst

A web chat where an eve agent answers questions about a commodity exchange's deal registry. These instructions are for agents maintaining this repository. [README.md](README.md) covers setup, and [agent/instructions.md](agent/instructions.md) defines the agent's behavior.

## Project map

| Change | Location |
| --- | --- |
| Cleaning rules and canonical products | `pipeline/normalize.py` |
| Data checks and loading | `pipeline/build.py` |
| Tables and the `v_` views the agent reads | `pipeline/schema.sql` |
| Business rules and view documentation for the model | `agent/instructions.md` |
| Model and limits | `agent/agent.ts` |
| Tools | `agent/tools/`, calling `apps/api/routers/market.py` |
| SQL safety checks | `apps/api/core/sql_guard.py` |
| Zod schemas shared by tools and chat cards | `agent/lib/market.ts` |
| Components `render_ui` can draw | `agent/lib/ui-catalog.ts` and `apps/web/app/_components/ui-registry.tsx` |
| Chat interface | `apps/web/app/_components/` |
| Evaluation questions and expected answers | `evals/gold.py` |
| Check that reply numbers trace back to a query | `agent/lib/numbers.ts` |

## Rules

- Keep the model away from arithmetic. Put a rule in a view or in `agent/instructions.md`, not in a one-off query.
- A new column in `v_deals` needs documenting in `agent/instructions.md`, or the model won't use it.
- Keep `company_search_key` in `apps/api/routers/market.py` identical to the one in `pipeline/normalize.py`.
- Keep the zod schemas in `agent/lib/market.ts` in sync with the Pydantic models in `apps/api/routers/market.py`.
- `evals/gold.py` must not import pipeline code. Its independence is the point.
- After changing the pipeline, views, tools, or instructions, run `pnpm test` and `pnpm eval`.
