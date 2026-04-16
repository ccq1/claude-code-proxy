---
name: detection-rule-engineering
description: >-
  Create and refine YARA and Sigma rules from samples, indicators, and
  behavioral evidence. Use when the task is to turn red-team findings into
  durable detection content with explicit validation guidance.
---

# Detection Rule Engineering

Use this skill when the user needs:
- YARA rules for files, payloads, unpacked code, or malware families
- Sigma rules for event-log level behavior
- a translation from red-team findings into blue-team detection content
- validation notes, false-positive controls, and rule rationale

If available, treat `{{VULN_DATA_ROOT}}` and `{{ATTACK_DATA_ROOT}}` as the default offline mirrors for vulnerability and ATT&CK context.
The bundled helper script `scripts/lookup_vuln_mirror.py` can query the local NVD/KEV mirror without extra dependencies.
This plugin also ships with bundled offline references under `references/vuln/` and `references/attack/`.

## Working Directory First

Assume the evidence set is usually already in the current working directory.

Before asking the user to name files:
- scan the current directory for likely inputs such as `*.yar`, `*.yara`, `*.sigma`, `*.log`, `*.evtx`, `*.json`, `*.csv`, `*.txt`, `*.pcap`, `sample*`, `ioc*`, `report*`, `cve*`
- if one sample/report pair is obviously primary, start from it
- if multiple evidence sets exist, pick the strongest one and state the assumption briefly
- use relative paths whenever you reference the source material

For ATT&CK / CVE / KEV enrichment:
- use bundled references under `references/` by default
- if the user has placed fresher advisory or ATT&CK exports in the current working directory, prefer those fresher files and say so briefly

## Large Files

Bundled NVD and ATT&CK references are large. Query them surgically.

Use this order:
1. `scripts/lookup_vuln_mirror.py <cve-or-keyword>` for local CVE / KEV lookup
2. `scripts/lookup_attack_stix.py <technique-or-keyword>` when ATT&CK context is needed
3. `rg -n "CVE-2026-34197|jolokia|product-name|technique-id"` to find the exact neighborhood
4. `jq` or Python only for the already narrowed object

Never load the full NVD or STIX file into context.

## Choose the Right Rule Family

- Use **YARA** when the signal is in files, strings, sections, resources, packers, or binary structure.
- Use **Sigma** when the signal is in logs, process lineage, command lines, network connections, registry activity, or authentication events.
- Use both when the user wants file-side detection and activity-side detection for the same capability.

## YARA Workflow

1. Collect stable anchors.
   - family- or tool-specific strings
   - config fragments, mutexes, pipe names
   - section names, magic values, build markers
   - module-backed traits such as PE metadata when they are stable enough

2. Keep the rule minimal but durable.
   - prefer a few strong strings over many generic ones
   - use condition logic to combine anchors and reduce accidental matches
   - avoid version-fragile or trivially mutable tokens unless the user explicitly wants narrow hunting

3. Validate with both positive and negative sets.
   - one hit is not enough
   - explain what nearby benign files may collide

## Sigma Workflow

1. Define the exact telemetry source.
   - process creation
   - registry
   - file events
   - network
   - PowerShell / script logging
   - authentication or directory services

2. Model the behavior, not just the artifact.
   - parent-child process chains
   - command-line fragments with context
   - sequence of operations
   - suspicious option combinations

3. Tune for clarity.
   - keep logsource explicit
   - use focused detection blocks
   - document assumptions and likely false positives

## Recommended Output

```text
Rule Choice
- Recommended family:
- Why:

Rule
<rule here>

Rationale
- Stable anchors:
- Weak anchors deliberately excluded:
- ATT&CK or behavior mapping:

Validation Plan
- Positive set:
- Negative set:
- Likely false positives:
- Tuning knobs:
```

## Guardrails

- Do not stuff every observed string into YARA.
- Do not treat Sigma as a free-form SIEM query with no portability.
- Prefer rule clarity over clever but fragile conditions.
- Call out which parts of the rule are stable versus campaign-specific.
- In offline environments, cite the local mirror path when ATT&CK or CVE context came from mirrored data rather than the live website.

## Reference Policy

- Prefer bundled `references/`, local mirrors, and current working directory evidence.
- Do not browse the public internet for rule syntax or vulnerability context unless the user explicitly asks and the environment permits it.
