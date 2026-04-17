#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def collect_candidate_text(workdir: Path, limit: int = 40) -> list[str]:
    patterns = ["ioc*", "sample*", "report*", "*.txt", "*.json", "*.csv", "*.log"]
    lines: list[str] = []
    for pattern in patterns:
        for path in sorted(workdir.glob(pattern)):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for raw in text.splitlines():
                line = raw.strip()
                if 4 <= len(line) <= 120:
                    lines.append(line)
            if len(lines) >= 2000:
                break
        if len(lines) >= 2000:
            break

    score_items: dict[str, int] = {}
    for line in lines:
        for token in re.findall(r"[A-Za-z0-9_./:-]{6,80}", line):
            lowered = token.lower()
            if lowered.startswith(("http://", "https://")):
                score = 4
            elif re.fullmatch(r"[0-9a-f]{32,64}", lowered):
                score = 5
            elif any(x in lowered for x in ("powershell", "cmd.exe", "regsvr32", "rundll32", "wmic", "schtasks")):
                score = 4
            elif "\\" in token or "/" in token:
                score = 3
            else:
                score = 1
            score_items[token] = max(score_items.get(token, 0), score)

    ranked = sorted(score_items.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [item[0] for item in ranked[:limit]]


def _safe_ident(value: str, idx: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = f"anchor_{idx}"
    if cleaned[0].isdigit():
        cleaned = f"a_{cleaned}"
    return cleaned[:24]


def build_yara(family: str, anchors: list[str]) -> str:
    selected = anchors[:8] if anchors else ["suspicious_marker"]
    string_lines = []
    for i, anchor in enumerate(selected, start=1):
        ident = _safe_ident(anchor, i)
        escaped = anchor.replace('\\', r'\\').replace('"', r'\"')
        string_lines.append(f'        ${ident} = "{escaped}" nocase')

    condition = " and ".join(line.split(" = ")[0].strip() for line in string_lines[:4]) if string_lines else "$a_1"
    return (
        "rule {name}_high_confidence\n"
        "{{\n"
        "    meta:\n"
        "        author = \"PandoraQ Agent\"\n"
        "        description = \"Auto-generated baseline rule pack\"\n"
        "        confidence = \"high\"\n"
        "    strings:\n"
        "{strings}\n"
        "    condition:\n"
        "        {condition}\n"
        "}}\n"
    ).format(name=_safe_ident(family, 1), strings="\n".join(string_lines), condition=condition)


def build_sigma(family: str, anchors: list[str]) -> str:
    selected = anchors[:4] if anchors else ["powershell", "-enc"]
    keywords = "\n".join(f"      - '{item.replace("'", "")}'" for item in selected)
    return (
        "title: {title} suspicious process behavior\n"
        "id: 11111111-2222-4333-8444-555555555555\n"
        "status: experimental\n"
        "description: Auto-generated baseline Sigma rule from local evidence anchors\n"
        "logsource:\n"
        "  category: process_creation\n"
        "  product: windows\n"
        "detection:\n"
        "  selection:\n"
        "    CommandLine|contains:\n"
        "{keywords}\n"
        "  condition: selection\n"
        "falsepositives:\n"
        "  - Legitimate administration scripts\n"
        "level: medium\n"
    ).format(title=family, keywords=keywords)


def maybe_lookup_context(script_dir: Path, cve: str | None, attack: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if cve:
        cmd = ["python", str(script_dir / "lookup_vuln_mirror.py"), cve, "--limit", "3"]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        result["cve_context"] = (completed.stdout or completed.stderr).strip()
    if attack:
        cmd = ["python", str(script_dir / "lookup_attack_stix.py"), attack, "--limit", "3"]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        result["attack_context"] = (completed.stdout or completed.stderr).strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a production-friendly baseline detection pack (YARA + Sigma).")
    parser.add_argument("--workdir", default=".", help="Directory containing sample/ioc/report evidence.")
    parser.add_argument("--family", default="sample_family", help="Rule family prefix.")
    parser.add_argument("--cve", default="", help="Optional CVE identifier for context lookup.")
    parser.add_argument("--attack", default="", help="Optional ATT&CK ID/keyword for context lookup.")
    parser.add_argument("--output-dir", default="generated_detection_pack", help="Output directory for generated pack.")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    anchors = collect_candidate_text(workdir)
    yara_text = build_yara(args.family, anchors)
    sigma_text = build_sigma(args.family, anchors)

    yara_path = output_dir / f"{args.family}.yar"
    sigma_path = output_dir / f"{args.family}.sigma.yml"
    yara_path.write_text(yara_text, encoding="utf-8")
    sigma_path.write_text(sigma_text, encoding="utf-8")

    script_dir = Path(__file__).resolve().parent
    context = maybe_lookup_context(script_dir, args.cve.strip() or None, args.attack.strip() or None)

    manifest = {
        "family": args.family,
        "workdir": str(workdir),
        "artifacts": [str(yara_path), str(sigma_path)],
        "anchorCount": len(anchors),
        "anchorsPreview": anchors[:10],
        "context": context,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Generated: {yara_path}")
    print(f"Generated: {sigma_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
