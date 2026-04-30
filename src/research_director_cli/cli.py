"""
Research Director CLI entry point.

Primary command shape: `rd "question"` — minimal positional usage.
Verbose alias: `research-director "question"`.

Flags:
  -o, --output PATH       Write output to PATH (default: brief-YYYY-MM-DD-HHMM.md in cwd)
  --no-json               Suppress the .json sidecar file (default: keep both)
  --print                 Print markdown to stdout instead of writing files
  --json-only             Write only the .json file (skip markdown rendering)
  -q, --quiet             Suppress progress messages
  --version               Show version and exit
  -h, --help              Show this help and exit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import run, write_outputs, render_brief


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rd",
        description=(
            "Research Director — structured deep-research with mechanically "
            "enforced output. Produces a brief with executive summary, sourced "
            "findings, gaps, and next steps."
        ),
        epilog=(
            "Examples:\n"
            "  rd \"What's the current state of agent SDKs in production?\"\n"
            "  rd \"Linear vs Jira for a 15-engineer team\" -o linear-jira.md\n"
            "  rd \"Red light therapy for tendinopathy\" --print | pbcopy\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "question",
        help="The research question. Wrap in quotes if it contains spaces.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "Output path. If a directory, files written there with a timestamped name. "
            "If a filename, used directly. Default: brief-YYYY-MM-DD-HHMM.md in cwd."
        ),
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Don't write the .json sidecar (default: write both .md and .json).",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print markdown to stdout instead of writing files.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Write/print only the JSON, skip markdown rendering.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress messages on stderr.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv)

    if args.print_only and args.output:
        parser.error("--print and --output are mutually exclusive.")

    def progress(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr, flush=True)

    progress(f"[rd] Running research on: {args.question!r}")
    progress("[rd] Turn 1 (research → JSON) — this typically takes 2–5 minutes.")

    try:
        result = run(args.question)
    except RuntimeError as e:
        print(f"\n[rd] Failed: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[rd] Interrupted.", file=sys.stderr)
        return 130

    progress(f"[rd] Turn 1 complete. Findings: {len(result.json_data['key_findings'])}, "
             f"Gaps: {len(result.json_data['gaps'])}, "
             f"Sources: {len(result.json_data['sources'])}")
    progress("[rd] Turn 2 (rendering markdown) — deterministic, no model call.")

    # Output
    if args.print_only:
        if args.json_only:
            print(json.dumps(result.json_data, indent=2))
        else:
            print(result.markdown)
        return 0

    output_path = Path(args.output) if args.output else None

    if args.json_only:
        # Write only the JSON file
        if output_path is None:
            from .core import default_output_basename
            json_path = Path.cwd() / f"{default_output_basename()}.json"
        else:
            json_path = output_path if output_path.suffix else output_path.with_suffix(".json")
        payload = {
            "question": result.question,
            "timestamp": result.timestamp,
            "data": result.json_data,
        }
        json_path.write_text(json.dumps(payload, indent=2))
        progress(f"[rd] Wrote {json_path}")
        return 0

    md_path, json_path = write_outputs(
        result,
        output_path=output_path,
        keep_json=not args.no_json,
    )
    progress(f"[rd] Wrote {md_path}")
    if json_path:
        progress(f"[rd] Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
