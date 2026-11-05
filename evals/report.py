"""Turns an `eve eval --json` report into evals/results/RESULTS.md and results.json.

    npx eve eval golden --url <deployment> --json > report.json
    python3 evals/report.py report.json --target <deployment> --model <model id>

Keeps what a reader needs to check each answer: the question, expected values, reply, queries, and
checks. Drops session IDs, traces, and token-by-token events.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
LANGUAGES = {"en": "English", "ru": "Russian", "uz": "Uzbek"}


def failed(check: dict) -> bool:
    return (
        check.get("passed", check.get("pass", True)) is False
        or check.get("status") == "failed"
        or check.get("verdict") == "failed"
    )


def check_name(check: dict) -> str:
    return str(check.get("label") or check.get("name") or "check")


def queries_and_results(events: list[dict]) -> list[dict]:
    calls: dict[str, dict] = {}
    for event in events:
        data = event.get("data") or {}
        if event.get("type") == "call.requested" and data["capability"]["name"] == "run_sql":
            calls[data["callId"]] = {"sql": data["input"].get("query", "")}
        elif event.get("type") == "call.settled" and data.get("callId") in calls:
            output = data.get("output") or {}
            calls[data["callId"]].update(
                columns=output.get("columns"),
                rows=(output.get("rows") or [])[:50],
                row_count=output.get("row_count"),
                error=output.get("error"),
                warning=output.get("warning"),
            )
    return list(calls.values())


def build(report: dict, gold: list[dict]) -> list[dict]:
    results = []
    for item in report["results"]:
        case = gold[int(re.search(r"(\d+)", item["id"].split("/")[-1]).group(1))]
        result = item["result"]
        checks = item.get("assertions") or []
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "language": case["lang"],
                "question": case["prompt"],
                "expected_numbers": [number["value"] for number in case["numbers"]],
                "expected_text": case["texts"],
                "passed": item.get("verdict") == "passed",
                "failed_checks": [check_name(check) for check in checks if failed(check)],
                "reply": result.get("reply") or "",
                "queries": queries_and_results(result.get("events") or []),
            }
        )
    return results


def cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


def markdown(results: list[dict], args: argparse.Namespace, started: str, history: str) -> str:
    passed = sum(result["passed"] for result in results)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_category[result["category"]].append(result)
    languages = Counter(result["language"] for result in results)
    language_passes = Counter(result["language"] for result in results if result["passed"])

    out = [
        "# Evaluation results",
        "",
        f"**{passed} of {len(results)} questions passed** on the live app.",
        "",
        "| | |",
        "| --- | --- |",
        f"| Target | {args.target} |",
        f"| Model | `{args.model}` |",
        f"| Run | {started[:16].replace('T', ' ')} UTC, one pass |",
        "| Questions | [evals/gold.py](../gold.py) |",
        "| Every answer in full | [results.json](results.json) |",
        "",
        "## How it's graded",
        "",
        "[evals/gold.py](../gold.py) computes the expected answers in pandas directly from the raw "
        "CSVs. It shares no code with the cleaning pipeline or the SQL views, so a bug there can't "
        "confirm itself.",
        "",
        "A question passes only if all of these hold:",
        "",
        "- The reply states each expected number, within 0.6% for amounts and exactly for counts.",
        "- The reply is in the language of the question.",
        "- Every number of 1,000 or more in the reply matches a value a query returned.",
        "- The agent called the expected tool, and no raw tool markup reached the reply.",
        "",
        "## Limits of this result",
        "",
        "- This is one pass. Earlier repeated runs varied, so an occasional slip can get through "
        "even though most questions passed here.",
        "- The questions were written by the team building the agent, not by real users.",
        "- Uzbek has few questions. A pass there is weaker evidence than in Russian or English.",
        "- A reply can pass while containing an extra wrong number below 1,000. Values drawn in "
        "charts and tables aren't checked against query results.",
        "- Grading looks for the expected number in the reply. It doesn't judge the wording.",
        "",
        "## Results by language",
        "",
        "| Language | Passed |",
        "| --- | --- |",
    ]
    for code, name in LANGUAGES.items():
        out.append(f"| {name} | {language_passes[code]} of {languages[code]} |")

    out += ["", "## Results by category", "", "| Category | Passed |", "| --- | --- |"]
    for category, rows in sorted(by_category.items()):
        out.append(f"| {category} | {sum(row['passed'] for row in rows)} of {len(rows)} |")

    failures = [result for result in results if not result["passed"]]
    out += ["", "## Failures", ""]
    for result in failures:
        out += [
            f"### `{result['id']}`",
            "",
            f"**Question:** {cell(result['question'])}",
            "",
            f"**Reply:** {cell(result['reply'])}",
            "",
            "**Failed checks:** " + "; ".join(cell(name) for name in result["failed_checks"]),
            "",
        ]
        if args.failure_note:
            out += [args.failure_note, ""]
    if not failures:
        out += ["None.", ""]

    out += ["## History", "", history.strip(), "", "## Every question", ""]
    for category, rows in sorted(by_category.items()):
        out += [f"### {category}", "", "| | Question | Reply |", "| --- | --- | --- |"]
        for row in rows:
            mark = "Pass" if row["passed"] else "**Fail**"
            reply = cell(row["reply"]) or "(asked which company was meant)"
            out.append(f"| {mark} | {cell(row['question'])} | {reply[:280]} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--failure-note", default="", help="Explanation added under each failure")
    args = parser.parse_args()

    report = json.loads(args.report.read_text())
    gold = json.loads((HERE / "data" / "golden.json").read_text())
    results = build(report, gold)

    folder = HERE / "results"
    folder.mkdir(exist_ok=True)
    history = (folder / "history.md").read_text()
    summary = {
        "target": args.target,
        "model": args.model,
        "started_at": report["startedAt"],
        "completed_at": report["completedAt"],
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "results": results,
    }
    (folder / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    (folder / "RESULTS.md").write_text(markdown(results, args, report["startedAt"], history))
    print(f"{summary['passed']} of {summary['total']} passed -> {folder}")


if __name__ == "__main__":
    main()
