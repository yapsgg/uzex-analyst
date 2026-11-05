"use client";

import type { EveToolPart } from "eve/react";
import { DatabaseIcon } from "lucide-react";
import type { ReactNode } from "react";

import { sqlResultSchema } from "../../../../agent/lib/market";

/**
 * Renders a dedicated card for a finished tool call.
 *
 * @param part - The tool part from the message.
 * @returns The card, or `undefined` to fall back to the generic tool display.
 */
export function renderToolCard(part: EveToolPart): ReactNode | undefined {
  if (part.state !== "completed" || part.name !== "run_sql") {
    return undefined;
  }
  const parsed = sqlResultSchema.safeParse(part.output);
  if (!parsed.success) {
    return undefined;
  }
  const input = part.input as { readonly query?: string; readonly purpose?: string } | undefined;
  return <SqlCard purpose={input?.purpose} query={input?.query} result={parsed.data} />;
}

const PREVIEW_ROWS = 10;

/** A collapsed record of one query, so anyone can check where a number came from. */
function SqlCard({
  purpose,
  query,
  result,
}: {
  readonly purpose: string | undefined;
  readonly query: string | undefined;
  readonly result: ReturnType<typeof sqlResultSchema.parse>;
}) {
  const summary =
    result.error === null
      ? `${result.row_count}${result.truncated ? "+" : ""} rows`
      : "Query failed, the agent retried";
  return (
    <details className="group bg-card w-full rounded-lg border text-sm">
      <summary className="text-muted-foreground hover:text-foreground flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs">
        <DatabaseIcon aria-hidden="true" className="size-3.5 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{purpose ?? "SQL query"}</span>
        <span className="shrink-0 tabular-nums">{summary}</span>
      </summary>
      <div className="space-y-2 border-t px-3 py-2">
        {query === undefined ? null : (
          <pre className="bg-muted overflow-x-auto rounded-md p-2 font-mono text-xs whitespace-pre-wrap">
            {query}
          </pre>
        )}
        {result.error === null ? null : <p className="text-xs">{result.error}</p>}
        {result.rows.length === 0 ? null : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground border-b text-left">
                  {result.columns.map((column) => (
                    <th className="py-1 pr-3 font-medium" key={column} scope="col">
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.slice(0, PREVIEW_ROWS).map((row, index) => (
                  <tr className="border-b last:border-0" key={index}>
                    {row.map((value, cell) => (
                      <td className="py-1 pr-3 tabular-nums" key={cell}>
                        {value === null ? "—" : String(value)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {result.rows.length > PREVIEW_ROWS ? (
              <p className="text-muted-foreground mt-1 text-xs">
                First {PREVIEW_ROWS} of {result.row_count}
                {result.truncated ? "+" : ""} rows.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </details>
  );
}
