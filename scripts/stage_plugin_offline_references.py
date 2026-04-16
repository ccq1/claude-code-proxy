#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


COPY_PLAN = {
    "attack-path-mapper": {
        "attack/enterprise-attack.json": "references/attack/enterprise-attack.json",
    },
    "detection-rule-engineering": {
        "attack/enterprise-attack.json": "references/attack/enterprise-attack.json",
        "vuln/known_exploited_vulnerabilities.json": "references/vuln/known_exploited_vulnerabilities.json",
        "vuln/nvdcve-2.0-recent.json": "references/vuln/nvdcve-2.0-recent.json",
    },
    "poc-engineering": {
        "vuln/known_exploited_vulnerabilities.json": "references/vuln/known_exploited_vulnerabilities.json",
        "vuln/nvdcve-2.0-recent.json": "references/vuln/nvdcve-2.0-recent.json",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy mirrored offline intel into plugin reference directories.")
    parser.add_argument(
        "--source-root",
        default="/root/pandoraq_open_intel",
        help="Root directory containing mirrored offline data.",
    )
    parser.add_argument(
        "--plugin-root",
        default=str(Path(__file__).resolve().parent / ".." / "app" / "plugin_marketplace" / "plugins"),
        help="Root directory of marketplace plugin bundles.",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    plugin_root = Path(args.plugin_root).expanduser().resolve()

    for plugin_name, mapping in COPY_PLAN.items():
        for relative_source, relative_dest in mapping.items():
            source = source_root / relative_source
            if not source.exists():
                raise FileNotFoundError(f"missing source dataset: {source}")
            dest = plugin_root / plugin_name / relative_dest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            print(f"[stage] {source} -> {dest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
