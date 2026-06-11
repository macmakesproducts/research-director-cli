> **📦 The Research Director _skill_ has moved.** Its canonical home is now **[macmakesproducts/researchdirector](https://github.com/macmakesproducts/researchdirector)** — install the portable, cross-platform skill from there. The legacy CLI-wrapper skill in `claude_code_skill/` is superseded; this repo remains the home of the Research Director _CLI_.

---

# Research Director CLI

A two-turn research tool that produces structurally-guaranteed research briefs.

```
                                          ┌────────────────────────┐
   "Linear vs Jira for 15           ──────│  Turn 1 (Claude API)   │
    engineers — what should               │  research → JSON       │
    we know before switching?"            └───────────┬────────────┘
                                                      │
                                                      ▼
                                          ┌────────────────────────┐
                                          │  Turn 2 (Python)       │
                                          │  JSON → markdown brief │
                                          └───────────┬────────────┘
                                                      │
                                                      ▼
                                              brief-*.md
                                              brief-*.json
```

## Why this exists

The original [Research Director](https://github.com/macmakesproducts/research-director) was a single-turn Claude skill — a SKILL.md file uploaded to claude.ai. After three iterations of escalating spec-strictness (`v1.2.0` → `v1.2.1` → `v1.2.2` adding "non-skippable" language, verbatim required headers, even a complete worked example baked into the spec), the produced briefs still ignored the structural contract while doing the underlying research well.

**Single-turn Claude skills can't enforce structural output contracts via prose instructions**. The model interprets prose-spec as a strong suggestion, not a requirement, and its own sense of what a "good research brief" looks like overrides the spec's prescribed shape.

The CLI architecture solves this by separating *research* (where Claude excels) from *rendering* (where determinism is required):

- **Turn 1** — Claude produces structured JSON. No formatting, no structural decisions. Just data.
- **Turn 2** — A Python template renders the JSON into the final markdown. No model. The structural contract IS the template.

The contract is mechanically enforced because Turn 2 has no latitude to "interpret" anything.

## Output structure (always)

Every brief contains these five sections, in this exact order, with these exact headers:

```
## Executive summary
## Key findings
## Open questions / gaps
## Recommended next steps
## Sources
```

Gap entries always carry the format: **statement** *(Category.)* Recommendation: action. Category is always one of: `Blind spot`, `Hallucination`, `Thin research`, `Missed consultation`, `Quality slippage`, `Drift`. Sources are always a consolidated block at the end with name, citation, recency, and reliability note when applicable.

## Install

```bash
pip install research-director
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

(Get one at https://console.anthropic.com/settings/keys)

## Use

```bash
rd "What's the current state of agent SDK ecosystems for production multi-agent systems?"
```

Outputs two files in the current directory:

```
brief-2026-04-30-1842.md     ← the rendered markdown brief
brief-2026-04-30-1842.json   ← the structured data the brief was rendered from
```

Cost per run: roughly $0.20–$0.80 in Anthropic API spend depending on how much research happens. Wall-clock time: typically 2–5 minutes.

### Common variants

```bash
# Specify output filename
rd "your question" -o linear-jira-evaluation.md

# Print to stdout instead of writing files
rd "your question" --print

# Pipe markdown to clipboard (macOS)
rd "your question" --print | pbcopy

# Skip the JSON sidecar
rd "your question" --no-json

# Get only the structured data
rd "your question" --json-only
```

Full flag reference: `rd --help`

## Three distribution layers

This tool ships in three forms depending on how you work:

### 1. CLI (this repo) — recommended

`pip install research-director`. Best for developers, scripts, and pipelines. Works in any terminal. Produces structurally-guaranteed output.

### 2. Claude Code skill

For [Claude Code](https://docs.claude.com/en/docs/claude-code) users. Drop the contents of `claude_code_skill/` into `~/.claude/skills/research-director/` (or per-project at `.claude/skills/research-director/`). Then in any Claude Code session:

```
/research-director "your question"
```

Or just describe what you want — Claude Code will auto-invoke the skill when the description matches. Under the hood it runs the same `rd` CLI, so you get the same structurally-guaranteed output.

### 3. Claude.ai skill (limited fallback)

The original [Research Director skill](https://github.com/macmakesproducts/research-director) still exists as a `.skill` upload for claude.ai users. It produces good research but **cannot mechanically enforce the output contract** — that's the limitation that motivated this CLI. Documented in that repo's CHANGELOG. Use when you don't have terminal access; the CLI is the recommended path.

## How it works (architecture)

### Turn 1 — Research

Claude (Opus 4.7) gets a system prompt focused entirely on producing structured JSON. It runs intake-equivalent reasoning, plans research, executes web search, names the cross-cutting synthesis pattern, and switches register to author the gaps adversarially against a six-flag taxonomy. Output is a single JSON object with these top-level fields:

```json
{
  "synthesis_pattern": "...",
  "executive_summary": "...",
  "key_findings": [...],
  "gaps": [...],
  "next_steps": [...],
  "sources": [...]
}
```

The full schema with field rules and validation is in [`src/research_director_cli/core.py`](src/research_director_cli/core.py).

### Turn 1 validation

Before rendering, the JSON is validated:

- All six top-level fields present
- `key_findings[].confidence` is one of `high`, `medium`, `low`
- `gaps[].category` is one of the six valid categories
- `gaps` is non-empty (research without gaps hallucinated its completeness)
- `sources` is non-empty

If validation fails, the run errors out with specific field-level messages — no malformed brief is rendered.

### Turn 2 — Render

A pure Python function takes the validated JSON and emits markdown using a deterministic template. No model involvement. The function is in [`src/research_director_cli/core.py`](src/research_director_cli/core.py) — read it; it's about 50 lines.

## Limitations

- **Requires terminal access.** The CLI doesn't run in claude.ai chat. Use the [.skill upload](https://github.com/macmakesproducts/research-director) as a fallback there, with the known structural-enforcement limitations.
- **Single-pass research.** No multi-step decomposition for very large topics yet. Heavy topics may produce a thinner brief than the same question would in claude.ai's research mode.
- **English only.** No localization yet.
- **No persistent memory across runs.** Each invocation is self-contained.

## Contributing

Issues and PRs welcome. The simplest contribution is reporting a brief that came out wrong — paste the question, what came out, and what you expected.

## License

MIT.

## Provenance

Built as part of the [Research Director](https://github.com/macmakesproducts/research-director) skill family. Companion eval harness: [research-director-evals](https://github.com/macmakesproducts/research-director-evals). The full design narrative — including why the original single-turn skill couldn't enforce its own contract — is documented in the build-out-loud notes.
