#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

STATUS_RE = re.compile(r"^status=(\d+)$")


def load_targets(path: Path) -> list[str]:
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(line)
    return items


def normalize_target(target: str, default_scheme: str) -> str:
    if target.startswith(("http://", "https://")):
        return target.rstrip("/")
    return f"{default_scheme}://{target.rstrip('/')}"


def resolve_verify_script(manifest_path: Path) -> Path:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for artifact in data.get("artifacts", []):
        candidate = Path(str(artifact)).expanduser().resolve()
        if candidate.name.endswith("_verify.py") and candidate.exists():
            return candidate
    raise FileNotFoundError(f"No *_verify.py artifact found in {manifest_path}")


def parse_status(stdout: str) -> int | None:
    for line in stdout.splitlines():
        match = STATUS_RE.match(line.strip())
        if match:
            return int(match.group(1))
    return None


def parse_verification_line(stdout: str) -> str:
    for line in stdout.splitlines():
        if line.lower().startswith("verification:"):
            return line.strip()
    return ""


def classify(returncode: int) -> str:
    if returncode == 0:
        return "strong_signal"
    if returncode == 2:
        return "weak_signal"
    return "failed"


def run_one(target: str, verify_script: Path, timeout: int, default_scheme: str) -> dict[str, object]:
    normalized_target = normalize_target(target, default_scheme)
    cmd = [sys.executable, str(verify_script), "--target", normalized_target, "--timeout", str(timeout)]
    start = time.time()

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, check=False)
        duration_ms = int((time.time() - start) * 1000)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "target": normalized_target,
            "result": classify(proc.returncode),
            "returncode": proc.returncode,
            "http_status": parse_status(stdout),
            "verification": parse_verification_line(stdout),
            "duration_ms": duration_ms,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "target": normalized_target,
            "result": "timeout",
            "returncode": 124,
            "http_status": None,
            "verification": "verification: timeout",
            "duration_ms": duration_ms,
            "stdout": "",
            "stderr": "process timeout",
        }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = ["target", "result", "http_status", "returncode", "duration_ms", "verification", "stderr"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def resolve_profile(profile: str) -> tuple[int, int, str]:
    presets = {
        "safe": (10, 15, "https"),
        "balanced": (20, 12, "https"),
        "aggressive": (40, 8, "http"),
    }
    if profile not in presets:
        raise ValueError(f"Unknown profile: {profile}")
    return presets[profile]


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-run generated safe verification scripts across many targets.")
    parser.add_argument("--targets-file", required=True, help="Text file with one target per line.")
    parser.add_argument("--verify-script", default="", help="Path to *_verify.py script. Optional if --manifest is provided.")
    parser.add_argument("--manifest", default="generated_poc_pack/manifest.json", help="Manifest path used to auto-resolve *_verify.py")
    parser.add_argument("--output-dir", default="batch_results", help="Directory for JSON/CSV results")
    parser.add_argument("--profile", default=None, choices=["safe", "balanced", "aggressive"], help="Preset runner profile.")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--timeout", type=int, default=15, help="Timeout passed to verify script")
    parser.add_argument("--default-scheme", default="https", choices=["http", "https"], help="Scheme used when target omits protocol")
    args = parser.parse_args()

    workers = args.workers
    timeout = args.timeout
    default_scheme = args.default_scheme
    if args.profile:
        workers, timeout, default_scheme = resolve_profile(args.profile)

    targets_path = Path(args.targets_file).expanduser().resolve()
    if not targets_path.exists():
        raise SystemExit(f"Targets file not found: {targets_path}")

    if args.verify_script:
        verify_script = Path(args.verify_script).expanduser().resolve()
        if not verify_script.exists():
            raise SystemExit(f"Verify script not found: {verify_script}")
    else:
        manifest_path = Path(args.manifest).expanduser().resolve()
        if not manifest_path.exists():
            raise SystemExit("Provide --verify-script or ensure --manifest exists.")
        verify_script = resolve_verify_script(manifest_path)

    targets = load_targets(targets_path)
    if not targets:
        raise SystemExit("No valid targets found in targets file.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(run_one, t, verify_script, timeout, default_scheme) for t in targets]
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: str(x.get("target", "")))
    stats = {
        "total": len(results),
        "strong_signal": sum(1 for r in results if r["result"] == "strong_signal"),
        "weak_signal": sum(1 for r in results if r["result"] == "weak_signal"),
        "failed": sum(1 for r in results if r["result"] == "failed"),
        "timeout": sum(1 for r in results if r["result"] == "timeout"),
    }

    summary = {
        "startedAt": started_at,
        "verifyScript": str(verify_script),
        "targetsFile": str(targets_path),
        "workers": workers,
        "timeout": timeout,
        "defaultScheme": default_scheme,
        "profile": args.profile or "custom",
        "stats": stats,
        "results": results,
    }

    json_path = output_dir / "batch_summary.json"
    csv_path = output_dir / "batch_results.csv"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, results)

    print(f"Verify script: {verify_script}")
    print(f"Targets: {len(targets)}")
    print(f"Stats: {stats}")
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
