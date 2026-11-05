import { defineEval } from "eve/evals";
import { satisfies } from "eve/evals/expect";
import { loadJson } from "eve/evals/loaders";
import { statesNumber, unsupportedNumbers } from "../agent/lib/numbers";

interface Expected {
  readonly value: number;
  readonly tol: number;
}
interface Case {
  readonly id: string;
  readonly category: string;
  readonly lang: string;
  readonly prompt: string;
  readonly numbers: readonly Expected[];
  readonly texts: readonly (readonly string[])[];
  readonly tool: string | null;
  readonly absent: readonly string[];
  readonly follow: { readonly prompt: string; readonly numbers: readonly Expected[] } | null;
}

/** Whether a reply is written in the case's language. Quoted names and code don't count. */
function inLanguage(reply: string, lang: string): boolean {
  const prose = reply.replace(/`[^`]*`|"[^"]*"|«[^»]*»/gu, "");
  const cyrillic = (prose.match(/[А-Яа-яЁёЎўҚқҒғҲҳ]/gu) ?? []).length;
  const latin = (prose.match(/[A-Za-z]/gu) ?? []).length;
  const share = cyrillic / Math.max(cyrillic + latin, 1);
  return lang === "ru" ? share > 0.5 : share < (lang === "en" ? 0.3 : 0.5);
}

/** Everything tools returned in a turn. */
function toolOutputs(turn: Turn): unknown[] {
  return turn.events.flatMap((event) =>
    event.type === "call.settled" ? [(event.data as { output?: unknown } | undefined)?.output] : [],
  );
}

const cases = (await loadJson("evals/data/golden.json")) as readonly Case[];

interface Turn {
  readonly reply?: string;
  readonly events: readonly { readonly type: string; readonly data?: unknown }[];
  readonly interactions: readonly unknown[];
}

/** The reply, plus anything drawn with render_ui or asked with ask_question. Query results don't count. */
function shown(turn: Turn): string {
  const visible = turn.events.flatMap((event) => {
    const data = event.data as { capability?: { name?: string }; input?: unknown } | undefined;
    const name = data?.capability?.name;
    return event.type === "call.requested" && (name === "render_ui" || name === "ask_question")
      ? [JSON.stringify(data?.input ?? "")]
      : [];
  });
  return [turn.reply ?? "", ...visible].join("\n");
}

export default cases.map((item) =>
  defineEval({
    description: `${item.id}: ${item.prompt}`,
    tags: [item.category, item.lang],
    async test(t) {
      const turn = await t.send(item.prompt);
      // Stopping to ask which company was meant is a valid outcome, not a stalled run.
      if (turn.interactions.length > 0) {
        t.awaitingInput();
      } else {
        t.succeeded();
      }
      if (item.tool) {
        t.calledTool(item.tool);
      }
      const text = shown(turn);
      t.log(`REPLY [${item.id}]: ${text}`);
      t.check(text, satisfies((value) => String(value).trim().length > 0, "reply is not empty"));
      if (turn.interactions.length === 0) {
        t.check(
          turn.reply ?? "",
          satisfies((reply) => inLanguage(String(reply), item.lang), `replies in ${item.lang}`),
        );
      }
      for (const { value, tol } of item.numbers) {
        t.check(text, satisfies((reply) => statesNumber(String(reply), value, tol), `states ${value}`));
      }
      for (const options of item.texts) {
        t.check(
          text.toLowerCase(),
          satisfies(
            (reply) => options.some((option) => String(reply).includes(option.toLowerCase())),
            `mentions one of: ${options.join(" | ")}`,
          ),
        );
      }
      t.check(text, satisfies((reply) => !String(reply).includes("DSML"), "no raw tool markup"));
      const sources = [item.prompt, toolOutputs(turn)];
      t.check(
        turn.reply ?? "",
        satisfies(
          (reply) => unsupportedNumbers(String(reply), sources).length === 0,
          `every number comes from a query: ${unsupportedNumbers(turn.reply ?? "", sources).join(", ") || "ok"}`,
        ),
      );
      for (const word of item.absent) {
        t.check(text, satisfies((reply) => !String(reply).includes(word), `omits ${word}`));
      }
      if (item.follow) {
        const next = await turn.session.send(item.follow.prompt);
        const followText = shown(next);
        t.log(`REPLY 2 [${item.id}]: ${followText}`);
        const allSources = [...sources, item.follow.prompt, toolOutputs(next)];
        t.check(
          next.reply ?? "",
          satisfies(
            (reply) => unsupportedNumbers(String(reply), allSources).length === 0,
            "every follow-up number comes from a query",
          ),
        );
        for (const { value, tol } of item.follow.numbers) {
          t.check(
            followText,
            satisfies((reply) => statesNumber(String(reply), value, tol), `follow-up states ${value}`),
          );
        }
      }
    },
  }),
);
