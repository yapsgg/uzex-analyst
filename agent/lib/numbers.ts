/**
 * Finds numbers in prose in any locale, with scale words such as "трлн", "mlrd", or "billion".
 *
 * Shared by the evaluation and the chat, so keep this module free of eve runtime and Node imports.
 */

const SCALES: readonly (readonly [RegExp, number])[] = [
  [/^(трлн|триллион\w*|trln|tn|trillion\w*)/iu, 1e12],
  [/^(млрд|миллиард\w*|mlrd|bn|billion\w*|milliard\w*)/iu, 1e9],
  [/^(млн|миллион\w*|mln|mn|million\w*)/iu, 1e6],
  [/^(тыс\w*|ming|thousand\w*|k\b)/iu, 1e3],
];

const NUMBER = /\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*/gu;

/** One literal can have two readings, as "1.234" may be 1234 or 1.234. Returns them all. */
function readings(literal: string): number[] {
  const text = literal.replace(/[   ]/gu, "");
  const dots = text.split(".").length - 1;
  const commas = text.split(",").length - 1;
  if (dots > 0 && commas > 0) {
    const decimal = text.lastIndexOf(".") > text.lastIndexOf(",") ? "." : ",";
    const thousands = decimal === "." ? "," : ".";
    return [Number(text.replaceAll(thousands, "").replace(decimal, "."))];
  }
  if (dots + commas === 0) {
    return [Number(text)];
  }
  const separator = dots > 0 ? "." : ",";
  const groups = text.split(separator);
  const grouped = groups.slice(1).every((group) => group.length === 3);
  const values: number[] = [];
  if (grouped) {
    values.push(Number(groups.join("")));
  }
  if (groups.length === 2) {
    values.push(Number(`${groups[0]}.${groups[1]}`));
  }
  return values;
}

export function extractNumbers(text: string): number[] {
  const found: number[] = [];
  for (const match of text.matchAll(NUMBER)) {
    const after = text.slice(match.index + match[0].length).replace(/^[\s  ]+/u, "");
    const scale = SCALES.find(([pattern]) => pattern.test(after))?.[1] ?? 1;
    for (const value of readings(match[0])) {
      found.push(value * scale);
    }
  }
  return found;
}

/** True when `text` states `expected` within the relative tolerance, in sign or absolute terms. */
export function statesNumber(text: string, expected: number, tolerance: number): boolean {
  const target = Math.abs(expected);
  return extractNumbers(text).some(
    (value) => Math.abs(value - target) <= Math.max(target * tolerance, 1e-9),
  );
}

/** Every number in a tool result, at any depth, including numbers inside strings. */
function toolNumbers(value: unknown, into: number[] = []): number[] {
  if (typeof value === "number") {
    into.push(Math.abs(value));
  } else if (typeof value === "string") {
    const parsed = Number(value);
    if (value.trim() !== "" && Number.isFinite(parsed)) {
      into.push(Math.abs(parsed));
    } else {
      into.push(...extractNumbers(value));
    }
  } else if (Array.isArray(value)) {
    for (const item of value) {
      toolNumbers(item, into);
    }
  } else if (value !== null && typeof value === "object") {
    for (const item of Object.values(value)) {
      toolNumbers(item, into);
    }
  }
  return into;
}

/**
 * Numbers of 1000 or more stated in a reply that no tool returned, allowing for display rounding.
 * This catches a model adding rows up itself. `sources` holds tool outputs and earlier messages.
 * Years and dates are ignored. Returns each number as it's written in the reply.
 */
export function unsupportedNumbers(reply: string, sources: readonly unknown[]): string[] {
  const known = toolNumbers(sources);
  const prose = reply
    .replace(/\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2}/gu, " ")
    .replace(/\b(19|20)\d{2}\b(?![ \u00a0\u202f]\d{3})/gu, " ");
  // A query can return an amount in billions while the reply says trillions, so any power of 1000
  // of a returned value is the same number.
  const matches = (value: number) =>
    known.some((other) =>
      [1, 1e3, 1e6, 1e9, 1e12].some((scale) => {
        const candidate = other * scale;
        return Math.abs(candidate - value) <= Math.max(value * 0.006, 0.5);
      }),
    );
  const missing = new Set<string>();
  // A literal can have two readings, so judge each literal, not each reading.
  for (const match of prose.matchAll(NUMBER)) {
    const after = prose.slice(match.index + match[0].length).replace(/^[\s\u00a0\u202f]+/u, "");
    const found = SCALES.find(([pattern]) => pattern.test(after));
    const raw = readings(match[0]);
    const scaled = raw.map((value) => value * (found?.[1] ?? 1));
    if (scaled.every((value) => value < 1000)) {
      continue;
    }
    if (!scaled.some(matches)) {
      const word = found ? after.match(found[0])?.[0] : undefined;
      missing.add(word ? `${match[0]} ${word}` : match[0]);
    }
  }
  return [...missing];
}
