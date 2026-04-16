---
name: evasion-analysis
description: >-
  Analyze anti-sandbox, anti-debug, anti-VM, and environment-gating behavior in
  malware or tooling. Use when a red-team task needs to explain how code hides,
  delays, or alters behavior in analysis environments.
---

# Evasion Analysis

Use this skill when the user wants to answer:
- Does this sample detect sandboxes, virtual machines, or analyst tooling?
- Which checks are actually gating payload execution?
- What would an analyst need to fake, patch, or emulate to trigger the real behavior?
- Which evasion behaviors matter operationally versus cosmetically?

## Working Directory First

Assume the relevant sample, report, or notes are already in the current working directory.

Before asking for additional parameters:
- scan the current directory for likely inputs such as `*.exe`, `*.dll`, `*.bin`, `*.ps1`, `*.js`, `strings*`, `sandbox*`, `trace*`, `api*`, `report*`, `notes*`
- if one sample or one report is clearly the focus, start immediately
- if multiple candidates exist, choose the most relevant and state the assumption briefly
- cite evidence with relative paths

## Large Files

Large sandboxes and API traces should be searched, not read end to end.

Use this order:
1. `rg -n` for sandbox markers, VM vendors, debugger APIs, sleep logic, and hook checks
2. read only the surrounding lines or the specific JSON objects that match
3. keep the analysis anchored to a short list of strong hits rather than a full trace dump

## Core Categories

Organize the analysis into these buckets:
- virtual machine and hypervisor artifacts
- sandbox and analysis tooling checks
- debugger and instrumentation checks
- user-activity or environment-quality checks
- timing, sleep, and delayed execution
- staged decryption or payload release gates

## What to Look For

### Environment fingerprinting

Look for checks involving:
- device drivers, services, registry keys, MAC OUIs
- BIOS strings, DMI values, vendor strings, hostname heuristics
- CPU count, RAM size, disk size, screen size, uptime
- running processes, modules, security tools, hooks, or tracing DLLs

### User-presence gating

Look for:
- mouse movement, keyboard activity, foreground window changes
- recent document count, browser history, desktop artifacts
- domain join state, locale, timezone, username quality

### Timing and patience

Look for:
- long sleep chains
- loop-based stalling
- API combinations that spread work across delayed stages
- execution that only continues after reboot, logon, or scheduled task windows

### Anti-debug and anti-instrumentation

Look for:
- `IsDebuggerPresent`, `CheckRemoteDebuggerPresent`
- `NtQueryInformationProcess`, debug object or debug flag checks
- SEH abuse, timing deltas, trap flags, exception tricks
- hook stripping, direct syscalls, integrity checks, or unhooking

## Analysis Workflow

1. Mark every environment check you can find.
2. Decide whether each one is:
   - `hard gate`: prevents core payload behavior
   - `soft gate`: degrades behavior or changes branch selection
   - `noise`: weak heuristic with little operational impact
3. Connect the check to its consequence.
   - exits process
   - withholds secondary payload
   - decrypts nothing
   - disables beaconing
   - suppresses credential theft, injection, or persistence
4. Summarize what must be emulated or patched to reproduce the true path.

## Output Template

```text
Evasion Summary
- Overall confidence:
- Primary gating family:
- Most important blockers:

Checks
- Check:
  category:
  evidence:
  effect if triggered:
  severity:

Reproduction Notes
- What to fake:
- What to patch:
- What to monitor after bypass:
```

## Guardrails

- Separate anti-analysis from ordinary environment adaptation.
- Not every sleep call is sandbox evasion; explain why it matters.
- Prefer exact evidence over long lists of possible APIs.
- Highlight the minimal change needed to confirm the gated branch.

## Reference Policy

- Prefer current working directory evidence and bundled/local ATT&CK material.
- Do not browse the public internet for sandbox-evasion context when local references are available.
