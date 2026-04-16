#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def resolve_vuln_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    plugin_root = Path(__file__).resolve().parents[1]
    runtime_path = plugin_root / "config" / "runtime.json"
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            configured_root = str(runtime.get("vulnDataRoot", "")).strip()
            if configured_root:
                configured_path = Path(configured_root).expanduser().resolve()
                if configured_path.exists():
                    return configured_path
        except Exception:
            pass

    return (plugin_root / "references" / "vuln").resolve()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_kev(root: Path) -> dict[str, dict]:
    path = root / "known_exploited_vulnerabilities.json"
    if not path.exists():
        return {}
    data = load_json(path)
    return {item["cveID"]: item for item in data.get("vulnerabilities", []) if item.get("cveID")}


def iter_nvd_items(root: Path):
    for name in ("nvdcve-2.0-recent.json", "nvdcve-2.0-modified.json"):
        path = root / name
        if not path.exists():
            continue
        data = load_json(path)
        for item in data.get("vulnerabilities", []):
            cve = item.get("cve", {})
            if cve:
                yield cve


def summarize_cve(cve: dict, kev_map: dict[str, dict]) -> str:
    cve_id = cve.get("id", "(unknown)")
    descriptions = cve.get("descriptions", [])
    desc = next((x.get("value", "") for x in descriptions if x.get("lang") == "en"), "")
    metrics = cve.get("metrics", {})
    severity = []
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if key in metrics:
            severity = metrics[key]
            break
    score = ""
    if severity:
        metric = severity[0]
        data = metric.get("cvssData", {})
        base_score = data.get("baseScore")
        base_severity = data.get("baseSeverity") or metric.get("baseSeverity")
        if base_score is not None:
            score = f"{base_score} {base_severity or ''}".strip()
    kev = kev_map.get(cve_id)
    line = f"{cve_id}"
    if score:
        line += f" | CVSS {score}"
    if kev:
        line += f" | KEV due {kev.get('dueDate', '')}"
    if desc:
        line += f"\n  desc: {' '.join(desc.split())[:280]}"
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description="Search a local vulnerability mirror (NVD + CISA KEV).")
    parser.add_argument("query", help="CVE ID or keyword")
    parser.add_argument(
        "--root",
        default=None,
        help="Optional path containing KEV and NVD mirror files. Defaults to configured override or bundled references.",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    root = resolve_vuln_root(args.root)
    kev_map = load_kev(root)
    query = args.query.lower()

    results: list[tuple[int, dict]] = []
    seen: set[str] = set()
    for cve in iter_nvd_items(root):
        cve_id = cve.get("id", "")
        if not cve_id or cve_id in seen:
            continue
        seen.add(cve_id)
        descs = " ".join(d.get("value", "") for d in cve.get("descriptions", []))
        score = 0
        if query in cve_id.lower():
            score += 10
        if query in descs.lower():
            score += 3
        if cve_id in kev_map:
            score += 1
        if score > 0:
            results.append((score, cve))

    results.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    if not results and args.query.upper() in kev_map:
        cve_id = args.query.upper()
        print(f"{cve_id} | present in CISA KEV")
        print(f"  due: {kev_map[cve_id].get('dueDate', '')}")
        print(f"  desc: {kev_map[cve_id].get('shortDescription', '')}")
        return 0

    for _, cve in results[: args.limit]:
        print(summarize_cve(cve, kev_map))

    if not results:
        print("No CVE entries matched the local mirror.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
