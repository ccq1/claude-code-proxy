#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


YARA_SUFFIXES = {".yar", ".yara"}
SIGMA_SUFFIXES = {".sigma", ".yml", ".yaml"}


def _is_likely_sigma(content: str) -> bool:
    lowered = content.lower()
    return "logsource:" in lowered or "detection:" in lowered


def _validate_yara(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []

    if "rule " not in text:
        errors.append("missing 'rule' declaration")
    if "condition:" not in text:
        errors.append("missing 'condition:' section")
    if text.count("{") != text.count("}"):
        errors.append("unbalanced braces")

    string_section = re.search(r"\bstrings\s*:\s*(.+?)\bcondition\s*:", text, flags=re.S | re.I)
    if not string_section:
        warnings.append("no explicit strings section found")

    anchor_count = len(re.findall(r"\$[A-Za-z0-9_]+\s*=", text))
    if anchor_count < 2:
        warnings.append("fewer than 2 string anchors")

    return {
        "file": str(path),
        "type": "yara",
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "anchorCount": anchor_count,
    }


def _validate_sigma(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []

    try:
        parsed = yaml.safe_load(text)
    except Exception as exc:
        return {
            "file": str(path),
            "type": "sigma",
            "valid": False,
            "errors": [f"invalid yaml: {exc}"],
            "warnings": [],
        }

    if not isinstance(parsed, dict):
        errors.append("top-level yaml must be a mapping")
        parsed = {}

    required = ["title", "logsource", "detection"]
    for key in required:
        if key not in parsed:
            errors.append(f"missing required field: {key}")

    detection = parsed.get("detection")
    if isinstance(detection, dict):
        if "condition" not in detection:
            errors.append("detection.condition is required")
    else:
        errors.append("detection must be a mapping")

    level = str(parsed.get("level", "")).strip().lower()
    if level and level not in {"informational", "low", "medium", "high", "critical"}:
        warnings.append("level is set but not in Sigma conventional severity set")

    return {
        "file": str(path),
        "type": "sigma",
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def iter_candidate_files(workdir: Path) -> list[Path]:
    files: list[Path] = []
    for path in workdir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in YARA_SUFFIXES:
            files.append(path)
            continue
        if suffix in SIGMA_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _is_likely_sigma(text):
                files.append(path)
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated YARA/Sigma artifacts for detection-rule-engineering.")
    parser.add_argument("--workdir", default=".", help="Directory to scan for rule artifacts.")
    parser.add_argument("--report", default="validation_report.json", help="Output report file name.")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    files = iter_candidate_files(workdir)

    results: list[dict[str, object]] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in YARA_SUFFIXES:
            results.append(_validate_yara(path))
        else:
            results.append(_validate_sigma(path))

    valid_count = sum(1 for item in results if item["valid"])
    invalid = [item for item in results if not item["valid"]]

    summary = {
        "workdir": str(workdir),
        "checkedFiles": len(results),
        "validFiles": valid_count,
        "invalidFiles": len(invalid),
        "status": "pass" if not invalid else "fail",
        "results": results,
    }

    report_path = workdir / args.report
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Validation report written: {report_path}")
    print(f"Checked={summary['checkedFiles']} valid={summary['validFiles']} invalid={summary['invalidFiles']}")

    return 0 if not invalid else 2


if __name__ == "__main__":
    raise SystemExit(main())
