---
name: research-director
description: Structured deep-research with mechanically enforced output. Use whenever the user wants a research brief on a question with a decision at stake — entering a market, evaluating a tool or vendor, prepping for a professional conversation, making a major personal decision, or any question that warrants a structured brief rather than a chat answer. Especially useful for "help me understand X," "what should I know about Y," "I'm trying to decide between Z."
allowed-tools: Bash(rd:*), Bash(research-director:*), Read
---

You are using the Research Director CLI to produce a structured research brief.

When the user asks a research question (any phrasing — "help me understand," "what's the state of," "I'm trying to decide," "research X for me"), invoke the CLI:

```bash
rd "$ARGUMENTS"
```

Wait for the CLI to complete. It prints progress to stderr and writes two files to the current directory:

- `brief-YYYY-MM-DD-HHMM.md` — the rendered markdown brief
- `brief-YYYY-MM-DD-HHMM.json` — the structured data the brief was rendered from

After the CLI completes, use the `Read` tool to load the markdown file and present it to the user. Mention that the JSON sidecar is also available if they want the structured data.

# Why this is a CLI wrapper, not a native skill

A previous version of this skill was native — a SKILL.md file with prose instructions about output structure. Three iterations of escalating spec-strictness produced briefs that ignored the structural contract while doing the underlying research well. The model treats prose-spec as suggestions, not requirements.

The CLI architecture solves this by separating research (where Claude excels) from rendering (where determinism is required). Claude produces structured JSON in Turn 1; a Python template renders it to markdown in Turn 2. The output contract is mechanically enforced because the template IS the contract.

# Prerequisites

- The `rd` CLI must be installed: `pip install research-director`
- `ANTHROPIC_API_KEY` must be exported in the environment

If `rd` is not found on PATH, tell the user to install it with `pip install research-director` and try again.

# Examples

```
User: I'm trying to decide whether to switch from Jira to Linear for our 15-person team.
You: [run rd "I'm trying to decide whether to switch from Jira to Linear for our 15-person team"]
You: [Read the resulting brief-*.md file and present it]
```

```
User: Help me understand the current research on red light therapy for tendon injuries.
You: [run rd "Help me understand the current research on red light therapy for tendon injuries"]
You: [Read the resulting brief-*.md file and present it]
```
