"use client";

import { useId, useMemo, useState } from "react";

import { cn } from "@/lib/utils";

/** Series colors from the validated data-viz palette, assigned in fixed order. */
const SERIES_VARS = ["--series-1", "--series-2", "--series-3", "--series-4"] as const;

const WIDTH = 640;
const HEIGHT = 260;
const PLOT = { top: 12, right: 12, bottom: 28, left: 56 };
const BAR_MAX = 24;

export interface MarketChartProps {
  /** `line` for change over time, `bar` for comparing categories. */
  readonly kind: "line" | "bar";
  readonly title: string;
  /** What the values measure, such as "млрд сум". */
  readonly unit: string;
  /** One label per point on the x axis. */
  readonly labels: readonly string[];
  readonly series: readonly { readonly name: string; readonly values: readonly (number | null)[] }[];
}

const compact = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, notation: "compact" });
const full = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

/** Round axis ticks that include zero, so bars and lines share an honest baseline. */
function ticks(max: number, min: number): number[] {
  const low = Math.min(0, min);
  const span = Math.max(max - low, 1e-9);
  const raw = span / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].find((m) => m * power >= raw) ?? 10) * power;
  const values: number[] = [];
  for (let v = Math.floor(low / step) * step; v < max + step; v += step) {
    values.push(v);
  }
  return values;
}

/** Bars or lines drawn in SVG, with hover and focus readouts and a table view. */
export function MarketChart({ kind, labels, series, title, unit }: MarketChartProps) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const shown = series.slice(0, SERIES_VARS.length);

  const geometry = useMemo(() => {
    const all = shown.flatMap((s) => s.values).filter((v): v is number => v !== null);
    const axis = ticks(Math.max(...all, 0), Math.min(...all, 0));
    const low = axis[0] ?? 0;
    const high = axis.at(-1) ?? 1;
    const innerW = WIDTH - PLOT.left - PLOT.right;
    const innerH = HEIGHT - PLOT.top - PLOT.bottom;
    const band = innerW / Math.max(labels.length, 1);
    return {
      axis,
      band,
      x: (index: number) => PLOT.left + band * (index + 0.5),
      y: (value: number) => PLOT.top + innerH * (1 - (value - low) / (high - low || 1)),
    };
  }, [labels.length, shown]);

  const everyNth = Math.max(1, Math.ceil(labels.length / 8));
  const baseline = geometry.y(0);
  const barWidth = Math.min(BAR_MAX, (geometry.band * 0.7) / Math.max(shown.length, 1));

  return (
    <figure className="market-chart bg-card w-full rounded-xl border p-4">
      <figcaption className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{title}</span>
        <button
          aria-expanded={showTable}
          className="text-muted-foreground hover:text-foreground shrink-0 text-xs underline-offset-2 hover:underline"
          onClick={() => setShowTable((value) => !value)}
          type="button"
        >
          {showTable ? "Hide table" : "Show table"}
        </button>
      </figcaption>
      {shown.length > 1 ? (
        <ul className="text-muted-foreground mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {shown.map((item, index) => (
            <li className="flex items-center gap-1.5" key={item.name}>
              <span
                aria-hidden="true"
                className="h-0.5 w-3 rounded-full"
                style={{ background: `var(${SERIES_VARS[index]})` }}
              />
              {item.name}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="relative">
        <svg
          aria-label={`${title}, ${unit}`}
          className="h-auto w-full"
          onPointerLeave={() => setActive(null)}
          role="img"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        >
          {geometry.axis.map((tick) => (
            <g key={tick}>
              <line
                stroke="var(--border)"
                x1={PLOT.left}
                x2={WIDTH - PLOT.right}
                y1={geometry.y(tick)}
                y2={geometry.y(tick)}
              />
              <text
                className="fill-muted-foreground text-[11px]"
                textAnchor="end"
                x={PLOT.left - 8}
                y={geometry.y(tick) + 4}
              >
                {compact.format(tick)}
              </text>
            </g>
          ))}
          {labels.map((label, index) =>
            index % everyNth === 0 ? (
              <text
                className="fill-muted-foreground text-[11px]"
                key={`${id}-${label}-${index}`}
                textAnchor="middle"
                x={geometry.x(index)}
                y={HEIGHT - 8}
              >
                {label.length > 12 ? `${label.slice(0, 11)}…` : label}
              </text>
            ) : null,
          )}
          {kind === "line" && active !== null ? (
            <line
              stroke="var(--muted-foreground)"
              x1={geometry.x(active)}
              x2={geometry.x(active)}
              y1={PLOT.top}
              y2={HEIGHT - PLOT.bottom}
            />
          ) : null}
          {shown.map((item, seriesIndex) => {
            const color = `var(${SERIES_VARS[seriesIndex]})`;
            if (kind === "bar") {
              return item.values.map((value, index) => {
                if (value === null) {
                  return null;
                }
                const left =
                  geometry.x(index) - (barWidth * shown.length) / 2 + barWidth * seriesIndex;
                const top = Math.min(geometry.y(value), baseline);
                const height = Math.max(Math.abs(baseline - geometry.y(value)), 1);
                const radius = Math.min(4, height, (barWidth - 2) / 2);
                const w = barWidth - 2;
                return (
                  <path
                    d={`M${left},${top + height}v${-(height - radius)}q0,${-radius} ${radius},${-radius}h${w - 2 * radius}q${radius},0 ${radius},${radius}v${height - radius}z`}
                    fill={color}
                    key={`${item.name}-${index}`}
                    opacity={active === null || active === index ? 1 : 0.45}
                  />
                );
              });
            }
            const segments: string[] = [];
            let pen = false;
            item.values.forEach((value, index) => {
              if (value === null) {
                pen = false;
                return;
              }
              segments.push(`${pen ? "L" : "M"}${geometry.x(index)},${geometry.y(value)}`);
              pen = true;
            });
            return (
              <g key={item.name}>
                <path
                  d={segments.join("")}
                  fill="none"
                  stroke={color}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                />
                {active !== null && item.values[active] != null ? (
                  <circle
                    cx={geometry.x(active)}
                    cy={geometry.y(item.values[active] as number)}
                    fill={color}
                    r={4}
                    stroke="var(--card)"
                    strokeWidth={2}
                  />
                ) : null}
              </g>
            );
          })}
          {labels.map((label, index) => (
            <rect
              aria-label={`${label}: ${shown.map((s) => `${s.name} ${s.values[index] ?? "—"}`).join(", ")}`}
              className="outline-none"
              fill="transparent"
              height={HEIGHT - PLOT.top - PLOT.bottom}
              key={`hit-${label}-${index}`}
              onBlur={() => setActive(null)}
              onFocus={() => setActive(index)}
              onPointerEnter={() => setActive(index)}
              tabIndex={0}
              width={geometry.band}
              x={geometry.x(index) - geometry.band / 2}
              y={PLOT.top}
            />
          ))}
        </svg>
        {active !== null ? (
          <div
            className="bg-popover text-popover-foreground pointer-events-none absolute top-1 z-10 max-w-56 rounded-md border px-2.5 py-1.5 text-xs shadow-sm"
            style={
              geometry.x(active) > WIDTH / 2
                ? { right: `${100 - (geometry.x(active) / WIDTH) * 100 + 2}%` }
                : { left: `${(geometry.x(active) / WIDTH) * 100 + 2}%` }
            }
          >
            <div className="text-muted-foreground mb-1">{labels[active]}</div>
            {shown.map((item, index) => (
              <div className="flex items-center gap-1.5" key={item.name}>
                <span
                  aria-hidden="true"
                  className="h-0.5 w-3 shrink-0 rounded-full"
                  style={{ background: `var(${SERIES_VARS[index]})` }}
                />
                <span className="font-medium tabular-nums">
                  {item.values[active] == null ? "—" : full.format(item.values[active] as number)}
                </span>
                {shown.length > 1 ? (
                  <span className="text-muted-foreground truncate">{item.name}</span>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <p className="text-muted-foreground mt-1 text-xs">{unit}</p>
      {showTable ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className={cn("text-muted-foreground border-b text-left")}>
                <th className="py-1 pr-3 font-medium" scope="col">
                  &nbsp;
                </th>
                {shown.map((item) => (
                  <th className="py-1 pr-3 text-right font-medium" key={item.name} scope="col">
                    {item.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labels.map((label, index) => (
                <tr className="border-b last:border-0" key={`row-${label}-${index}`}>
                  <th className="py-1 pr-3 text-left font-normal" scope="row">
                    {label}
                  </th>
                  {shown.map((item) => (
                    <td className="py-1 pr-3 text-right tabular-nums" key={item.name}>
                      {item.values[index] == null ? "—" : full.format(item.values[index] as number)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </figure>
  );
}
