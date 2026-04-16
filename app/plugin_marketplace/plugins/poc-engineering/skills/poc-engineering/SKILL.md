---
name: poc-engineering
description: >-
  Turn exploit ideas, advisories, and one-off checks into reusable POC or
  validation templates. Use when a red-team task needs reproducible request
  flows, variable extraction, preconditions, and low-noise verification logic.
---

# POC Engineering

Use this skill when the user asks for:
- turning a loose exploit idea into a reusable template
- converting a one-off curl or script into a repeatable check
- building a nuclei-style workflow with matchers, extractors, and guardrails
- reducing false positives in vulnerability validation

If `{{VULN_DATA_ROOT}}` is configured, use it as the default offline source for CVE, KEV, and mirrored advisory context.
The bundled helper script `scripts/lookup_vuln_mirror.py` can query the local NVD/KEV mirror without extra dependencies.
This plugin also ships with bundled offline vulnerability references under `references/vuln/`.

## Working Directory First

Assume the user usually puts advisories, requests, POC drafts, or captures into the current working directory.

Before asking for parameters:
- scan the current directory for likely inputs such as `*.http`, `*.txt`, `*.md`, `*.json`, `*.yaml`, `*.pcap`, `*.har`, `request*`, `response*`, `poc*`, `exploit*`, `cve*`, `advisory*`
- if one exploit note or request trace is clearly primary, start from it
- if several candidates exist, choose the most relevant one and state the assumption briefly
- cite inputs with relative paths

For CVE / KEV context:
- use bundled references under `references/vuln/` by default
- if the user has placed a fresher advisory set in the current working directory, prefer that fresher set and say so briefly

## Large Files

Bundled vulnerability mirrors can be large. Query them in layers.

Use this order:
1. `scripts/lookup_vuln_mirror.py <cve-or-keyword>` for fast local lookup
2. `rg -n "CVE-...|product|endpoint|parameter"` on advisories, request traces, and notes
3. `jq` or Python only when you already know which object or field you need
4. read only the relevant request/response fragments, not the whole trace

Never dump the full mirrored JSON into context.

## Default Posture

Default to **safe validation first**:
- confirm product and version
- verify the vulnerable code path exists
- use low-impact probes when possible
- keep destructive or state-changing steps behind an explicit user request

## Engineering Workflow

1. Define the target contract.
   - product / version / deployment assumptions
   - auth requirements
   - protocol and state needs
   - success condition versus side effect

2. Separate the flow into stages.
   - fingerprint
   - prerequisite checks
   - exploit or validation request
   - extraction of dynamic values
   - success matcher
   - false-positive suppression

3. Pick the right implementation form.
   - Nuclei template for HTTP-heavy, mostly declarative checks
   - Python or Bash harness when state, crypto, or multi-step logic is complex
   - hybrid output when a simple template plus a reproduction script helps delivery

4. Add engineering quality.
   - timeouts and retries
   - redirect handling
   - auth token capture
   - CSRF or nonce extraction
   - deduplication and idempotence
   - explicit cleanup steps when state changes are unavoidable

## Output Pattern

When possible, provide:
- a short operator summary
- the template or script
- required variables
- expected success and failure signals
- false-positive notes
- any assumptions that make the POC environment-specific

## Template Checklist

- metadata clearly scoped
- product fingerprint included
- at least one strong matcher
- negative guard if the signal is noisy
- extractor logic for dynamic tokens when needed
- note on safe mode versus full exploitation

## Guardrails

- Do not hide risky side effects.
- Do not confuse a version guess with exploitation success.
- Explain which part of the flow is the actual proof.
- If the only signal is brittle, say that the template is best-effort rather than high-confidence.
- In offline environments, distinguish what came from the local mirror versus what still needs fresh vendor validation.

## Reference Policy

- Prefer bundled vulnerability references, working directory materials, and admin-provided internal documentation.
- Do not browse the public internet for template or advisory context unless the user explicitly asks for online research.
