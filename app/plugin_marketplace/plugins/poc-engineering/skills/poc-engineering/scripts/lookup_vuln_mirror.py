#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
            if configured_root:
                configured_path = Path(configured_root).expanduser().resolve()
                if configured_path.exists():
                    return configured_path
        except Exception:
            pass

    return (skill_root / "references" / "vuln").resolve()


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
    query = args.query.lower()
    results: list[tuple[int, str, str, bool]] = []
    seen: set[str] = set()

    for cve in iter_nvd_items(root):
        cve_id = cve.get("id", "")
        if not cve_id or cve_id in seen:
            continue
        seen.add(cve_id)
        desc = next((x.get("value", "") for x in cve.get("descriptions", []) if x.get("lang") == "en"), "")
        score = 0
        if query in cve_id.lower():
            score += 10
        if query in desc.lower():
            score += 3
        if score > 0:
            results.append((score, cve_id, " ".join(desc.split())[:280], cve_id in kev_map))

    results.sort(key=lambda item: (-item[0], item[1]))
    for _, cve_id, desc, in_kev in results[: args.limit]:
        suffix = " | KEV" if in_kev else ""
        print(f"{cve_id}{suffix}")
        if desc:
            print(f"  desc: {desc}")

    if not results:
        print("No vulnerability entries matched the local mirror.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
