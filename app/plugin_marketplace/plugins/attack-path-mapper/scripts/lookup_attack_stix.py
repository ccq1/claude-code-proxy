#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def resolve_attack_file(explicit_file: str | None) -> Path:
    if explicit_file:
        return Path(explicit_file).expanduser().resolve()

    plugin_root = Path(__file__).resolve().parents[1]
    runtime_path = plugin_root / "config" / "runtime.json"
    if runtime_path.exists():
        try:
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            configured_root = str(runtime.get("attackDataRoot", "")).strip()
            if configured_root:
                configured_path = Path(configured_root).expanduser()
                if configured_path.is_dir():
                    candidate = configured_path / "enterprise-attack.json"
                    if candidate.exists():
                        return candidate.resolve()
                elif configured_path.exists():
                    return configured_path.resolve()
        except Exception:
            pass

    return (plugin_root / "references" / "attack" / "enterprise-attack.json").resolve()


def load_attack_patterns(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    objects = data.get("objects", [])
    return [obj for obj in objects if obj.get("type") == "attack-pattern" and not obj.get("revoked")]


def score(pattern: dict, query: str) -> int:
    q = query.lower()
    name = pattern.get("name", "").lower()
    ext_ids = " ".join(
        ref.get("external_id", "")
        for ref in pattern.get("external_references", [])
        if isinstance(ref, dict)
    ).lower()
    description = pattern.get("description", "").lower()
    s = 0
    if q in ext_ids:
        s += 10
    if q in name:
        s += 6
    if q in description:
        s += 2
    return s


def main() -> int:
    parser = argparse.ArgumentParser(description="Search local MITRE ATT&CK STIX enterprise data.")
    parser.add_argument("query", help="Technique ID or keyword, e.g. T1497 or Kerberoasting")
    parser.add_argument(
        "--file",
        default=None,
        help="Optional path to enterprise-attack.json. Defaults to configured override or bundled references.",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    attack_file = resolve_attack_file(args.file)
    patterns = load_attack_patterns(attack_file)
    ranked = sorted(
        ((score(p, args.query), p) for p in patterns),
        key=lambda item: (-item[0], item[1].get("name", "")),
    )

    shown = 0
    for points, pattern in ranked:
        if points <= 0:
            continue
        ext_ids = [
            ref.get("external_id", "")
            for ref in pattern.get("external_references", [])
            if isinstance(ref, dict) and ref.get("external_id")
        ]
        print(f"{', '.join(ext_ids[:2]) or '(no id)'} | {pattern.get('name', '(no name)')}")
        tactics = [
            phase.get("phase_name", "")
            for phase in pattern.get("kill_chain_phases", [])
            if isinstance(phase, dict) and phase.get("phase_name")
        ]
        if tactics:
            print(f"  tactics: {', '.join(tactics)}")
        description = " ".join(pattern.get("description", "").split())
        if description:
            print(f"  desc: {description[:280]}")
        shown += 1
        if shown >= args.limit:
            break

    if shown == 0:
        print("No ATT&CK techniques matched the query.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
