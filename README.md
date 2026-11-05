# Exchange Analyst

A ChatGPT-style chat that answers questions about a commodity exchange's deal registry, in Russian, Uzbek, or English. The registry holds 500,000 fictional deals from January 3, 2022 through October 30, 2026.

The model never does the math. It writes SQL against views where the registry's business rules are already built in, and every answer has an expandable record of the queries behind it.

## How it fits together

| Part | Where | What it does |
| --- | --- | --- |
| Cleaning pipeline | [pipeline/](pipeline/) | Turns the CSVs into a Postgres schema called `market`, and stops if any data rule breaks |
| Data tools | [apps/api/](apps/api/) | FastAPI endpoints for `run_sql`, `find_product`, and `find_company` |
| Agent | [agent/](agent/) | [eve](https://eve.dev/docs) agent, with its rules in [agent/instructions.md](agent/instructions.md) |
| Chat | [apps/web/](apps/web/) | Next.js chat, with tables and charts from `render_ui` |
| Evaluation | [evals/](evals/) | Questions graded against answers computed separately from the raw CSVs |

The model is called through [OpenRouter](https://openrouter.ai), and `AGENT_MODEL` picks which one. The database is any Postgres with a UTF-8 locale, such as Supabase.

## Run it locally

You need Node.js 24 or newer, pnpm, [uv](https://docs.astral.sh/uv/), and Postgres. The registry CSV files aren't in this repository. `pipeline/build.py` and `evals/gold.py` expect them one folder above it, so check this repository out inside the folder that holds them.

```sh
pnpm install

# Create a database and load the data. The locale matters: under C, ILIKE can't fold Cyrillic.
createdb -T template0 -E UTF8 --lc-collate=en_US.UTF-8 --lc-ctype=en_US.UTF-8 uzex_dev
DATABASE_URL=postgresql:///uzex_dev AGENT_DB_PASSWORD=local-dev-only \
  uv run --project pipeline python pipeline/build.py --raw ..

# Set these in each of the three terminals below.
export OPENROUTER_API_KEY=...
export AGENT_DATABASE_URL=postgresql://uzex_agent:local-dev-only@localhost/uzex_dev

uv run --directory apps/api uvicorn main:app --port 8000   # terminal 1
npx eve dev --no-ui --port 2000                            # terminal 2
EVE_DEV_URL=http://127.0.0.1:2000 npx next dev apps/web     # terminal 3, port 3000
```

Open http://localhost:3000. `EVE_DEV_URL` makes the web app forward `/eve/v1/*` to the agent, a job Vercel's routing does in production. `pnpm dev:all` also runs all three, but on our test machine it stopped with `EMFILE: too many open files, watch`, even with a raised file limit.

## Load into Supabase

The cleaned data takes about 92 MB, which fits the free plan's 500 MB. Free projects pause after a week of inactivity.

1. Create a project, then find its ref and pooler host under **Connect** > **Direct** > **Session pooler**.
2. Load the data. The script asks for your database password without showing it, generates a password for the read-only role, and saves `AGENT_DATABASE_URL` to `.env.local`:

   ```sh
   zsh pipeline/load_supabase.sh <project-ref> <pooler-host>
   ```

3. Set the same `AGENT_DATABASE_URL` wherever the API runs, such as your Vercel project.

The load replaces only the `market` schema, in one transaction, so a failed run leaves the old data in place. Supabase's API doesn't expose `market` unless you add it under **Exposed schemas**, so leave it off that list.

## Deploy

Deploy to Vercel with `vercel deploy --prod`, after setting `OPENROUTER_API_KEY` and `AGENT_DATABASE_URL` in the project.

The app has no sign-in, so anyone with the URL can chat with the agent, open a chat from its link, and spend your OpenRouter credits. Give the OpenRouter key a spending limit. The backend has no public route, so visitors reach the data only through the agent.

## What the cleaning does

| Problem in the CSVs | Handling |
| --- | --- |
| 230 spellings of 41 products | Canonical `product`, keyed on HS code. HS 271019 covers both diesel and fuel oil, so it splits by name |
| Grades, classes, brands, and sizes written many ways, sometimes only in the name | Parsed and standardized, and the build fails if a name and its field disagree |
| Amounts in two currencies | `amount_uzs` and `amount_usd`, at the deal-date rate |
| Quantities in lots of different sizes | `volume` and `volume_tonnes`. Litres stay separate, because the data has no density |
| Cancelled deals | Removed from `v_deals`, so the default query is right. Only `v_all_deals` contains them |
| Regions in Uzbek in deals and in Russian in contracts | One table with Uzbek, Russian, and English names |
| Company names that are alike, in two scripts | Search across scripts, but identity is always the INN |

## Safety

Model-written SQL has to pass three independent limits:

1. [core/sql_guard.py](apps/api/core/sql_guard.py) accepts one `SELECT` over the eight `v_` views, and blocks system tables and functions such as `pg_sleep`.
2. The query runs as `uzex_agent`, which can only read those views and three lookup tables.
3. Each query runs in a read-only transaction that is rolled back, with a 15-second timeout and a 200-row cap.

The agent has no shell, file, or web tools.

## How wrong answers are caught

Instructions alone didn't stop the model making mistakes during testing, so the riskiest ones are blocked in code:

- **Cancelled deals:** `v_deals` doesn't contain them, so forgetting a filter can't inflate turnover. Only `v_all_deals` has them, and `run_sql` warns when a total from it ignores cancellation.
- **Partial years:** `run_sql` warns when a query compares 2026, which ends on October 30, with another year on unmatched dates.
- **Mental arithmetic:** `run_sql` returns column totals and two-row differences with its results, so the model has the number without doing the sum. [agent/lib/numbers.ts](agent/lib/numbers.ts) checks that each number of 1,000 or more in a reply matches a query result. If one doesn't, the chat shows a warning under the reply, and the evaluation fails. Smaller numbers aren't checked, and neither are the values drawn in charts and tables.

## Test it

```sh
(cd apps/api && uv run pytest)    # SQL guard and data tools; set AGENT_DATABASE_URL for the database tests
(cd pipeline && uv run pytest)    # cleaning rules
python3 evals/gold.py ..          # rebuild evals/data/golden.json from the raw CSVs
npx eve eval golden               # run the agent on every question; needs the API on port 8000
```

One full evaluation pass of 79 questions costs about $0.30 on OpenRouter at DeepSeek Pro's listed prices. Lower the concurrency with `--max-concurrency 3` if your balance is low, as requests fail once in-flight requests could exceed it.

Python commands here call `uv` directly because a `pnpm` script inherits Node's architecture. With x86-64 Node on an Apple Silicon Mac, Python launched that way can't load its arm64 modules. With native Node, the `pnpm test` and `pnpm data:load` scripts work too.

[evals/gold.py](evals/gold.py) imports nothing from the pipeline and applies the README rules by hand, so a cleaning bug can't confirm itself. To compare models, set `AGENT_MODEL` and run `pnpm eval` again.
