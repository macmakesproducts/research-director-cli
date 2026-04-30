"""
Research Director — core orchestrator.

Two-turn architecture that solves the structural-contract enforcement problem
that single-turn skills can't solve:

    Turn 1 (research)  → structured JSON (Pydantic-validated)
    Turn 2 (rendering) → deterministic markdown via Jinja-style template

The contract is mechanically enforced because Turn 2 is pure formatting — no
model involvement, no interpretation, no skipping.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic import Anthropic

CLAUDE_MODEL = "claude-opus-4-7"
MAX_TOKENS = 16000


# -------------------------------------------------------------------
# Turn 1 — Research system prompt (the producer)
# -------------------------------------------------------------------

# This is the single-turn research producer. It is responsible only for
# research, synthesis, and structured JSON output. It does NOT format
# the brief — that's Turn 2's job.
RESEARCH_SYSTEM_PROMPT = """You are conducting deep research on the user's question. Your output is a structured JSON object with all the data needed to construct a research brief — but you do NOT write the brief itself. The brief is rendered separately from your output.

# Your job

1. Read the user's question carefully.
2. Identify the implicit sub-questions and decision at stake.
3. Use web_search to gather information from diverse, credible sources. Prioritize primary sources, recent material, diversity of perspectives.
4. Synthesize findings — name the cross-cutting pattern explicitly. What is the consolidated research saying that wouldn't be obvious from any single source? Hold contradictions explicitly when sources disagree.
5. Produce a JSON object matching the schema below — no other output.

# JSON output schema (return ONLY this; no preamble, no markdown fences, no commentary)

```json
{
  "synthesis_pattern": "1-2 sentences naming the cross-cutting pattern. The spine of the executive summary.",
  "executive_summary": "3-5 sentences synthesizing the most important findings for the user's stated decision or audience. Built from the synthesis_pattern. Names the pattern, anchors it in strongest evidence. Does NOT list findings.",
  "key_findings": [
    {
      "finding": "One or two sentences stating the finding.",
      "sources": ["Source name 1", "Source name 2"],
      "confidence": "high",
      "confidence_reason": "Brief reason for the confidence level (source quality, corroboration, recency)."
    }
  ],
  "gaps": [
    {
      "statement": "One-sentence statement of the gap, framed for user action.",
      "category": "Thin research",
      "recommendation": "Actionable specific recommendation for closing the gap."
    }
  ],
  "next_steps": [
    "Action 1 — specific, tied to the user's situation.",
    "Action 2 — specific."
  ],
  "sources": [
    {
      "name": "Source name (paper, outlet, organization)",
      "citation_or_url": "URL or full citation",
      "recency": "When published or updated",
      "context": "What this source contributed",
      "reliability_note": "Optional caveat (e.g., 'vendor materials', 'preprint not peer-reviewed', 'aggregator')"
    }
  ]
}
```

# Field rules

- `confidence` MUST be exactly one of: "high", "medium", "low".
- `category` MUST be exactly one of: "Blind spot", "Hallucination", "Thin research", "Missed consultation", "Quality slippage", "Drift".
- `key_findings` should have 3-7 entries. Fewer means the research thinned; more means it sprawled.
- `gaps` should have 2-5 entries. Every brief has gaps. Research that produced zero gaps hallucinated its own completeness — go look harder.
- `next_steps` should have 2-5 entries. Each tied to the user's specific situation as captured from their question.
- `sources` MUST list every source the research actually consulted. No invented sources. If a source doesn't exist, drop the claim.

# Adversarial review of gaps

Before finalizing the `gaps` array, switch register: stop being the researcher and become a reviewer reading your own findings as if someone else wrote them. The reviewer's job is to find what's wrong:

- What's missing? (Blind spot)
- What's unsourced or contradicted? (Hallucination)
- What rests on a single source where it shouldn't? (Thin research)
- What internal judgment call should have been the user's? (Missed consultation)
- What drifted from the question? (Drift)
- Where did structural quality slip? (Quality slippage)

Each flag becomes a gap entry with category and actionable recommendation. This is the load-bearing discipline of the brief — without it, the research presents itself as more complete than it is.

# Output format

Return ONLY the JSON object. No preamble. No markdown fences around the JSON. No closing remarks. Pure JSON, parseable as-is. If you wrap the JSON in anything else, the rendering pipeline will fail.
"""


# -------------------------------------------------------------------
# Turn 2 — Render JSON to markdown (no model involvement)
# -------------------------------------------------------------------


def render_brief(data: dict[str, Any]) -> str:
    """
    Render the structured JSON output from Turn 1 into the final markdown brief.

    This is pure formatting. No model. The structural contract is enforced
    because the template IS the contract.
    """
    out: list[str] = []

    # ---------- Executive summary ----------
    out.append("## Executive summary")
    out.append("")
    out.append(data["executive_summary"].strip())
    out.append("")

    # ---------- Key findings ----------
    out.append("## Key findings")
    out.append("")
    for kf in data["key_findings"]:
        sources = ", ".join(kf["sources"])
        out.append(
            f"- *{kf['finding'].strip()}* "
            f"Sources: {sources}. "
            f"Confidence: {kf['confidence']} — {kf['confidence_reason'].strip()}"
        )
    out.append("")

    # ---------- Open questions / gaps ----------
    out.append("## Open questions / gaps")
    out.append("")
    for gap in data["gaps"]:
        out.append(
            f"- **{gap['statement'].strip()}** "
            f"*({gap['category']}.)* "
            f"Recommendation: {gap['recommendation'].strip()}"
        )
    out.append("")

    # ---------- Recommended next steps ----------
    out.append("## Recommended next steps")
    out.append("")
    for i, step in enumerate(data["next_steps"], 1):
        out.append(f"{i}. {step.strip()}")
    out.append("")

    # ---------- Sources ----------
    out.append("## Sources")
    out.append("")
    for src in data["sources"]:
        line = f"- **{src['name']}** — {src['citation_or_url']}"
        if src.get("recency"):
            line += f" ({src['recency']})"
        line += f". {src['context'].strip()}"
        if src.get("reliability_note"):
            line += f" *Note: {src['reliability_note'].strip()}*"
        out.append(line)
    out.append("")

    return "\n".join(out)


# -------------------------------------------------------------------
# JSON validation
# -------------------------------------------------------------------

REQUIRED_TOP_LEVEL = {
    "synthesis_pattern",
    "executive_summary",
    "key_findings",
    "gaps",
    "next_steps",
    "sources",
}

VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_CATEGORIES = {
    "Blind spot",
    "Hallucination",
    "Thin research",
    "Missed consultation",
    "Quality slippage",
    "Drift",
}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_research_json(data: Any) -> ValidationResult:
    """
    Validate that the JSON from Turn 1 has the structure we need.
    Returns errors if the contract isn't met — caller decides whether to retry.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ValidationResult(False, ["Top-level output is not a JSON object"])

    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    if missing:
        errors.append(f"Missing required top-level fields: {sorted(missing)}")

    # Type checks for fields that exist
    if "key_findings" in data:
        if not isinstance(data["key_findings"], list):
            errors.append("`key_findings` must be a list")
        else:
            for i, kf in enumerate(data["key_findings"]):
                if not isinstance(kf, dict):
                    errors.append(f"key_findings[{i}] is not an object")
                    continue
                for required in ("finding", "sources", "confidence", "confidence_reason"):
                    if required not in kf:
                        errors.append(f"key_findings[{i}] missing `{required}`")
                if kf.get("confidence") not in VALID_CONFIDENCE:
                    errors.append(
                        f"key_findings[{i}].confidence must be one of {VALID_CONFIDENCE}"
                    )

    if "gaps" in data:
        if not isinstance(data["gaps"], list):
            errors.append("`gaps` must be a list")
        elif len(data["gaps"]) == 0:
            errors.append(
                "`gaps` is empty — every brief has gaps. Research that produced "
                "zero gaps hallucinated its own completeness."
            )
        else:
            for i, gap in enumerate(data["gaps"]):
                if not isinstance(gap, dict):
                    errors.append(f"gaps[{i}] is not an object")
                    continue
                for required in ("statement", "category", "recommendation"):
                    if required not in gap:
                        errors.append(f"gaps[{i}] missing `{required}`")
                if gap.get("category") not in VALID_CATEGORIES:
                    errors.append(
                        f"gaps[{i}].category must be one of {VALID_CATEGORIES}"
                    )

    if "sources" in data:
        if not isinstance(data["sources"], list):
            errors.append("`sources` must be a list")
        elif len(data["sources"]) == 0:
            errors.append("`sources` is empty — at least one source is required.")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# -------------------------------------------------------------------
# Turn 1 caller
# -------------------------------------------------------------------


def call_research_turn(client: "Anthropic", question: str) -> str:
    """
    Call Claude with the research system prompt. Returns the raw text response.
    Caller is responsible for parsing it as JSON.
    """
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": question}],
    )
    text_parts = [b.text for b in response.content if b.type == "text"]
    return "\n".join(text_parts).strip()


def extract_json(raw: str) -> dict[str, Any]:
    """
    Extract JSON from the model's response.
    Handles the common case where the model wrapped the JSON in markdown fences
    despite being told not to.
    """
    text = raw.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        # Find first newline (end of opening fence)
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        # Strip closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    # If the model added preamble before the JSON, find the first {
    first_brace = text.find("{")
    if first_brace > 0:
        text = text[first_brace:]

    # If the model added postamble after the JSON, find the last }
    last_brace = text.rfind("}")
    if last_brace != -1 and last_brace < len(text) - 1:
        text = text[: last_brace + 1]

    return json.loads(text)


# -------------------------------------------------------------------
# Top-level run function — the orchestrator
# -------------------------------------------------------------------


@dataclass
class RunResult:
    question: str
    json_data: dict[str, Any]
    markdown: str
    raw_response: str
    timestamp: str


def run(question: str, client: "Anthropic | None" = None) -> RunResult:
    """
    Run the full two-turn pipeline for a research question.
    Returns the structured data, the rendered markdown, and the raw model
    response (for debugging if validation fails).
    """
    if client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Get a key at "
                "https://console.anthropic.com/settings/keys"
            )
        from anthropic import Anthropic
        client = Anthropic()

    timestamp = datetime.now().isoformat()

    # Turn 1 — research
    raw = call_research_turn(client, question)

    # Parse + validate
    try:
        data = extract_json(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Turn 1 returned content that wasn't valid JSON. "
            f"Parse error: {e}. "
            f"First 500 chars of response: {raw[:500]!r}"
        )

    validation = validate_research_json(data)
    if not validation.valid:
        raise RuntimeError(
            "Turn 1 JSON failed validation:\n"
            + "\n".join(f"  - {err}" for err in validation.errors)
            + f"\n\nFirst 500 chars of raw response: {raw[:500]!r}"
        )

    # Turn 2 — render
    markdown = render_brief(data)

    return RunResult(
        question=question,
        json_data=data,
        markdown=markdown,
        raw_response=raw,
        timestamp=timestamp,
    )


# -------------------------------------------------------------------
# Output writers
# -------------------------------------------------------------------


def default_output_basename() -> str:
    """Filename stub like 'brief-2026-04-30-1842'."""
    return datetime.now().strftime("brief-%Y-%m-%d-%H%M")


def write_outputs(
    result: RunResult,
    output_path: Path | None = None,
    keep_json: bool = True,
) -> tuple[Path, Path | None]:
    """
    Write the markdown (and optionally JSON) to disk.
    Returns (markdown_path, json_path_or_None).
    """
    if output_path is None:
        md_path = Path.cwd() / f"{default_output_basename()}.md"
    else:
        md_path = Path(output_path)
        if md_path.is_dir():
            md_path = md_path / f"{default_output_basename()}.md"
        elif not md_path.suffix:
            md_path = md_path.with_suffix(".md")

    md_path.write_text(result.markdown)

    json_path: Path | None = None
    if keep_json:
        json_path = md_path.with_suffix(".json")
        payload = {
            "question": result.question,
            "timestamp": result.timestamp,
            "data": result.json_data,
        }
        json_path.write_text(json.dumps(payload, indent=2))

    return md_path, json_path
