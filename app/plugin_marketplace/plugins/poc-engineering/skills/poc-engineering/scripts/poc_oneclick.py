#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def resolve_script(path: Path, name: str) -> Path:
    candidate = path / name
    if not candidate.exists():
        raise SystemExit(f"Required script not found: {candidate}")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="One-click POC engineering pipeline (scaffold + batch verify).")
    parser.add_argument("--workdir", default=".", help="Case directory containing request sample and targets.txt")
    parser.add_argument("--name", default="incident_case", help="POC name prefix")
    parser.add_argument("--profile", default="balanced", choices=["safe", "balanced", "aggressive"], help="Verification profile")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent batch workers")
    parser.add_argument("--timeout", type=int, default=12, help="Per-target timeout seconds")
    parser.add_argument("--default-scheme", default="https", choices=["http", "https"], help="Scheme for targets without protocol")
    parser.add_argument("--targets-file", default="", help="Optional explicit targets file path")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    scaffold_script = resolve_script(script_dir, "scaffold_poc.py")
    batch_script = resolve_script(script_dir, "run_batch_verify.py")

    workdir = Path(args.workdir).expanduser().resolve()
    if not workdir.exists():
        raise SystemExit(f"Workdir not found: {workdir}")

    profile_map = {
        "safe": {"success": "200", "signal": "401,403", "keyword": ""},
        "balanced": {"success": "200,204", "signal": "401,403", "keyword": "success"},
        "aggressive": {"success": "200,201,202,204", "signal": "400,401,403,405", "keyword": ""},
    }
    profile = profile_map[args.profile]

    scaffold_cmd = [
        sys.executable,
        str(scaffold_script),
        "--workdir",
        str(workdir),
        "--name",
        args.name,
        "--success-status",
        profile["success"],
        "--signal-status",
        profile["signal"],
    ]
    if profile["keyword"]:
        scaffold_cmd.extend(["--success-keyword", profile["keyword"]])

    print("[oneclick] step=generate")
    gen = subprocess.run(scaffold_cmd, check=False)
    if gen.returncode != 0:
        return gen.returncode

    manifest_path = workdir / "generated_poc_pack" / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found after scaffold: {manifest_path}")

    targets_file = Path(args.targets_file).expanduser().resolve() if args.targets_file else (workdir / "targets.txt")
    if not targets_file.exists():
        raise SystemExit(f"Targets file not found: {targets_file}")

    batch_cmd = [
        sys.executable,
        str(batch_script),
        "--targets-file",
        str(targets_file),
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(workdir / "batch_results"),
        "--workers",
        str(args.workers),
        "--timeout",
        str(args.timeout),
        "--default-scheme",
        args.default_scheme,
    ]

    print("[oneclick] step=batch")
    run = subprocess.run(batch_cmd, check=False)
    if run.returncode != 0:
        return run.returncode

    print(f"[oneclick] done. summary={workdir / 'batch_results' / 'batch_summary.json'}")
    print(f"[oneclick] done. csv={workdir / 'batch_results' / 'batch_results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
