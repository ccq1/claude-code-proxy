---
name: attack-path-mapper
description: >-
  Build plausible red-team attack chains from footholds, identities, and asset
  relationships. Use when the user needs lateral movement, privilege
  escalation, or crown-jewel reachability planning grounded in evidence.
---

# Attack Path Mapper

Use this skill when the user asks:
- How do we get from the current foothold to a target system or data set?
- Which lateral movement or privilege-escalation route is most realistic?
- How should observed behavior map to ATT&CK tactics and techniques?
- What is the shortest path with acceptable noise and operational risk?

If `{{ATTACK_DATA_ROOT}}` is configured, use the local ATT&CK STIX mirror there before reaching for the public ATT&CK website.
The bundled helper script `scripts/lookup_attack_stix.py` can be used for quick offline technique lookup.
This plugin also ships with bundled offline ATT&CK references under `references/attack/`.

## Working Directory First

Assume the user will place exports and notes in the current working directory.

Before asking for missing context:
- scan the current directory for likely evidence such as `*.json`, `*.csv`, `*.txt`, `*.md`, `bloodhound*`, `nodes*`, `edges*`, `sessions*`, `creds*`, `hosts*`, `acl*`, `notes*`
- if one dataset obviously matches the task, start from it
- if multiple datasets could apply, pick the most relevant one and state the assumption in one short sentence
- cite evidence with relative paths

For ATT&CK mapping specifically:
- use bundled offline data under `references/attack/` by default
- if the user has put a newer ATT&CK export in the current working directory, prefer the newer local copy and say so briefly

## Large Files

Bundled ATT&CK STIX is large. Do not read it wholesale.

Use this order:
1. `scripts/lookup_attack_stix.py <query>` for fast offline lookup
2. `rg -n "T1497|Kerberoast|WinRM|RDP"` on the local exports or notes
3. `jq` or Python only after the result set is already narrowed
4. read only short surrounding excerpts when you need evidence text

Never `cat` the full STIX JSON into context.

## Required Inputs

You do not need all of these, but the skill is much stronger with them:
- current foothold or starting identity
- reachable subnets or trust boundaries
- local admin / domain privileges / group memberships
- known credentials, tokens, or delegation edges
- reachable services, shares, or management interfaces
- target objective: DA, Tier-0 asset, database, mailbox, CI/CD, etc.
- any of the above if already exported into the current working directory

## Planning Workflow

1. Define the start state and the objective.
   - Start state: what access is already confirmed?
   - Objective: what exact host, identity, secret, or data set matters?
   - Constraints: stealth, speed, tooling limits, user restrictions.

2. Build candidate edges.
   - Credential edges: reused credentials, delegation, cached secrets, tickets, vault access.
   - Service edges: SMB, WinRM, RDP, SSH, MSSQL, vCenter, CI/CD agents, remote management.
   - Identity edges: group nesting, ACL abuse, shadow admins, constrained/unconstrained delegation.
   - Application edges: admin panels, orchestration systems, SaaS tokens, build pipelines.

3. Convert edges into chains.
   - Prefer chains with explicit evidence over broad theoretical possibilities.
   - For each hop, list prerequisites, tooling assumptions, and expected evidence of success.

4. Map to ATT&CK only after the path is concrete.
   - Use ATT&CK to annotate, not to replace reasoning.
   - A short chain with clear evidence beats a dense matrix of guessed techniques.

5. Select a recommended route.
   - Rank by probability of success, noise, operator effort, and blast radius.
   - Keep at least one alternate route if the primary path depends on a brittle assumption.

## Output Model

Use a structured answer:

```text
Recommended Route
1. Step:
   prerequisite:
   evidence:
   expected result:
   likely detection surface:

Alternative Routes
- Route:
  why it exists:
  blocker:

Key Unknowns
- Unknown:
  why it matters:
  fastest validation:
```

## Evidence Rules

- Separate observed edges from inferred edges.
- Mark each hop as `confirmed`, `likely`, or `speculative`.
- Never assume reachability, credential validity, or privilege inheritance without saying so.

## ATT&CK Usage

Use ATT&CK to summarize the chain after you have the path:
- tactic progression
- technique names and IDs where confidence is high
- likely detections or mitigations per hop

In offline deployments, prefer the local STIX mirror under `{{ATTACK_DATA_ROOT}}`.

## Guardrails

- Do not produce sprawling attack graphs with no prioritization.
- Do not force every path to match ATT&CK coverage goals.
- Call out blockers early: segmentation, MFA, PAM, EDR, tiering, JIT elevation.
- Prefer the path that is easiest to validate with minimal operational noise.

## Reference Policy

- Prefer bundled `references/attack/`, local mirrors, and current working directory exports.
- Do not browse the public internet for ATT&CK context when local material is available.
