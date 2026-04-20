#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def resolve_layout() -> tuple[Path, Path]:
    script_path = Path(__file__).resolve()
    skill_root = script_path.parents[1]
    for candidate in script_path.parents:
        if (candidate / ".claude-plugin" / "plugin.json").exists():
            return skill_root, candidate
    return skill_root, skill_root.parents[1]


def resolve_vuln_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    skill_root, plugin_root = resolve_layout()
    runtime_path = plugin_root / "config" / "runtime.json"
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            configured_root = str(runtime.get("vulnDataRoot", "")).strip()
            if configured_root and configured_root != "{{VULN_DATA_ROOT}}":
                configured_path = Path(configured_root).expanduser().resolve()
                if configured_path.exists():
                    return configured_path
        except (json.JSONDecodeError, OSError):
            pass

    return (skill_root / "references" / "vuln").resolve()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_kev(root: Path) -> dict[str, dict]:
    path = root / "known_exploited_vulnerabilities.json"
    if not path.exists():
        return {}
    try:
        data = load_json(path)
    except (json.JSONDecodeError, OSError):
        return {}
    return {item["cveID"]: item for item in data.get("vulnerabilities", []) if item.get("cveID")}


def iter_nvd_items(root: Path):
    for name in ("nvdcve-2.0-recent.json", "nvdcve-2.0-modified.json"):
        path = root / name
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        for item in data.get("vulnerabilities", []):
            cve = item.get("cve", {})
            if cve:
                yield cve


def extract_cvss(cve: dict) -> str:
    metrics = cve.get("metrics", {})
    metric_groups = ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2")
    for group in metric_groups:
        group_values = metrics.get(group, [])
        if not group_values:
            continue
        first = group_values[0]
        cvss_data = first.get("cvssData", {})
        base_score = cvss_data.get("baseScore")
        base_severity = cvss_data.get("baseSeverity") or first.get("baseSeverity")
        if base_score is not None:
            severity = f"/{base_severity}" if base_severity else ""
            return f"{base_score}{severity}"
    return "n/a"


def tokenize_query(query: str) -> list[str]:
    parts = [x for x in re.split(r"[^a-zA-Z0-9._-]+", query.lower()) if x]
    return parts or [query.lower()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Query a local NVD/KEV mirror for POC engineering context.")
    parser.add_argument("query", help="CVE ID or keyword")
    parser.add_argument(
        "--root",
        default=None,
        help="Optional path containing mirrored vulnerability data. Defaults to configured override or bundled references.",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    root = resolve_vuln_root(args.root)
    kev_map = load_kev(root)

    existing_files = [
        p.name
        for p in [
            root / "known_exploited_vulnerabilities.json",
            root / "nvdcve-2.0-recent.json",
            root / "nvdcve-2.0-modified.json",
        ]
        if p.exists()
    ]

    print(f"[mirror] root={root}")
    if not existing_files:
        print("[mirror] no mirror files found. expected known_exploited_vulnerabilities.json and/or nvdcve-2.0-*.json")
        return 1

    query_tokens = tokenize_query(args.query)
    results: list[tuple[int, str, str, bool, str, str]] = []
    seen: set[str] = set()

    for cve in iter_nvd_items(root):
        cve_id = cve.get("id", "")
        if not cve_id or cve_id in seen:
            continue
        seen.add(cve_id)

        desc = next((x.get("value", "") for x in cve.get("descriptions", []) if x.get("lang") == "en"), "")
        desc_lower = desc.lower()
        cve_lower = cve_id.lower()

        score = 0
        for token in query_tokens:
            if token in cve_lower:
                score += 12
            if token in desc_lower:
                score += 3

        if score <= 0:
            continue

        kev_entry = kev_map.get(cve_id, {})
        kev_due = kev_entry.get("dueDate", "")
        cvss = extract_cvss(cve)
        results.append((score, cve_id, " ".join(desc.split())[:280], cve_id in kev_map, kev_due, cvss))

    results.sort(key=lambda item: (-item[0], item[1]))
    for _, cve_id, desc, in_kev, kev_due, cvss in results[: args.limit]:
        kev_suffix = " | KEV" if in_kev else ""
        due_suffix = f" | due={kev_due}" if kev_due else ""
        print(f"{cve_id}{kev_suffix} | cvss={cvss}{due_suffix}")
        if desc:
            print(f"  desc: {desc}")

    if not results:
        print("No vulnerability entries matched the local mirror.")
        print(f"Hint: files available under mirror root: {', '.join(existing_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
