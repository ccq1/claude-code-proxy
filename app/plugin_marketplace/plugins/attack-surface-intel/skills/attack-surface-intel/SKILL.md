---
name: attack-surface-intel
description: >-
  Turn domains, IPs, URLs, hashes, and organization clues into prioritized
  attack-surface findings. Use when a red-team task needs passive
  infrastructure pivots, exposed-service triage, or entry-point hypotheses,
  including offline or air-gapped environments.
---

# Attack Surface Intelligence

Use this skill when the user wants to answer questions like:
- Which domains, hosts, URLs, or samples are most relevant to a target?
- What internet-exposed assets look valuable for initial access?
- Which pieces of infrastructure appear shared, historical, or suspicious?
- Which findings are facts, and which are only pivots or hypotheses?

## Working Directory First

Assume the user will usually place the needed inputs in the current working directory.

Before asking for parameters:
- scan the current directory and a few levels of subdirectories for likely inputs
- prefer obvious files such as `*.csv`, `*.json`, `*.txt`, `*.xlsx`, `domains*`, `assets*`, `inventory*`, `ioc*`, `cert*`, `nmap*`, `hosts*`
- if one candidate set is clearly dominant, use it immediately
- if several candidates exist, choose the most relevant set and briefly state the assumption
- when citing evidence, prefer relative paths

This skill is for passive and low-noise attack-surface work. It is strongest when the input is one or more of:
- domain / subdomain
- IP address / CIDR
- URL
- file hash
- TLS certificate clue
- organization, product, or brand name
- local asset inventory or CMDB export
- IOC spreadsheet, JSON export, or passive scan snapshot

## Offline-First Mode

Assume the deployment may be air-gapped.

Prefer these local sources first:
- asset inventory exports
- Nmap or banner snapshots
- passive DNS / certificate exports already present on disk
- IOC spreadsheets or JSON bundles
- malware sample indexes, sandbox reports, and internal incident notes
- files already present in the current working directory

If `{{INTEL_WORKSPACE}}` is configured, treat it as the default root for local intelligence artifacts. Only reach for internet intelligence if the environment allows it and the user actually needs it.

## Core Workflow

1. Normalize the starting indicators.
   - Canonicalize domains, URLs, hashes, ports, and organization names.
   - Separate target-owned assets from third-party services, CDNs, and shared SaaS.

2. Pull passive intelligence first.
   - In offline environments, start from local exports, snapshots, and previously collected passive data.
   - If external access exists, VirusTotal or similar passive lookup can enrich files, URLs, domains, IPs, and relationships.
   - Use passive DNS, certificate, and exposed-service data to find pivots whether the source is local or remote.

3. Build infrastructure pivots.
   - Group by certificate, ASN, registrar, name server, favicon, banner, or hosting provider.
   - Distinguish current infrastructure from stale or historical overlap.
   - Note whether the pivot is strongly owned, weakly related, or only adjacent noise.

4. Prioritize entry points.
   - Score findings by reachability, authentication exposure, exploitability, and relevance to the engagement objective.
   - Favor assets that plausibly lead to foothold, credential capture, or application-layer validation.

5. Produce evidence and next actions.
   - Facts: directly observed and reproducible.
   - Pivots: related infrastructure that needs confirmation.
   - Hypotheses: promising paths that still need validation.

## Source Preference

Use sources in this order:
1. Local asset inventories, incident artifacts, and internal knowledge bases
2. Previously collected passive intelligence exports and snapshots
3. Official platform or vendor documentation
4. High-quality passive intelligence platforms
5. Security vendor writeups and incident reports
6. Generic search results only as a starting point

Do not turn a single reputation signal into a strong conclusion. Reputation, geolocation, and shared-hosting overlap are weak by themselves.

## Optional API Patterns

If the user has configured local or remote sources, these placeholders may be available:
- `{{INTEL_WORKSPACE}}`
- `{{VT_API_KEY}}`
- `{{SHODAN_API_KEY}}`
- `{{CENSYS_API_ID}}`
- `{{CENSYS_API_SECRET}}`

Typical uses:
- Local workspace: inventories, IOC bundles, exported scan results, certificate or passive DNS snapshots
- VirusTotal: search and relationship pivots for file / URL / domain / IP objects
- Shodan: exposed services, open ports, and banners
- Censys: certificate-centric and host-centric passive discovery

## Output Format

Use a compact structure:

```text
Target Surface Summary
- Scope anchor:
- Highest-value ingress candidates:
- Shared infrastructure or pivots:
- Historical or noisy observations:

Evidence Table
- Indicator:
  type:
  observation:
  confidence:
  next validation step:

Recommended Next Actions
- Action 1:
- Action 2:
- Action 3:
```

## Guardrails

- Prefer passive intelligence before active probing.
- In air-gapped deployments, prefer local evidence over synthetic guesses.
- Keep third-party shared infrastructure clearly labeled.
- Always state when the evidence is historical, cached, or indirectly inferred.
- If the user asks for active validation, first identify the lowest-noise check that proves or disproves the hypothesis.

## Reference Policy

- Do not browse the public internet just because the skill mentions enrichment options.
- Prefer current working directory, bundled `references/`, local mirrors, and admin-provided internal services.
- Only use a remote source if the user explicitly asks for it and the environment actually permits it.
