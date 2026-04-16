#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen, Request


ATTACK_ENTERPRISE_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
)
CISA_KEV_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
)
NVD_RECENT_URL = (
    "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-recent.json.gz"
)
NVD_MODIFIED_URL = (
    "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-modified.json.gz"
)
CVELIST_GIT_URL = "https://github.com/CVEProject/cvelistV5.git"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "pandoraq-open-intel-sync/1.0"})
    with urlopen(req, timeout=120) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def download_gzip_json(url: str, dest: Path) -> None:
    gz_path = dest.with_suffix(dest.suffix + ".gz")
    download(url, gz_path)
    with gzip.open(gz_path, "rb") as source, dest.open("wb") as target:
        shutil.copyfileobj(source, target)


def maybe_git_sync(repo_url: str, dest: Path) -> None:
    if dest.exists():
        subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"], check=True)
        return
    subprocess.run(["git", "clone", "--depth", "1", repo_url, str(dest)], check=True)


def write_manifest(root: Path, entries: dict[str, str]) -> None:
    manifest = {
        "root": str(root),
        "datasets": entries,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync open-source threat/vulnerability feeds for offline PandoraQ use.")
    parser.add_argument(
        "--root",
        default="/var/lib/pandoraq/open-intel",
        help="Target root directory for mirrored datasets.",
    )
    parser.add_argument(
        "--with-cvelist",
        action="store_true",
        help="Also clone or update the official CVEProject/cvelistV5 repository (large).",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    attack_root = root / "attack"
    vuln_root = root / "vuln"
    cve_root = root / "cve"

    attack_file = attack_root / "enterprise-attack.json"
    kev_file = vuln_root / "known_exploited_vulnerabilities.json"
    nvd_recent_file = vuln_root / "nvdcve-2.0-recent.json"
    nvd_modified_file = vuln_root / "nvdcve-2.0-modified.json"

    print(f"[sync] root={root}")
    print("[sync] downloading ATT&CK enterprise STIX")
    download(ATTACK_ENTERPRISE_URL, attack_file)

    print("[sync] downloading CISA KEV")
    download(CISA_KEV_URL, kev_file)

    print("[sync] downloading NVD recent feed")
    download_gzip_json(NVD_RECENT_URL, nvd_recent_file)

    print("[sync] downloading NVD modified feed")
    download_gzip_json(NVD_MODIFIED_URL, nvd_modified_file)

    entries = {
        "attack.enterprise": str(attack_file),
        "vuln.cisa_kev": str(kev_file),
        "vuln.nvd_recent": str(nvd_recent_file),
        "vuln.nvd_modified": str(nvd_modified_file),
    }

    if args.with_cvelist:
        print("[sync] cloning/updating CVEProject cvelistV5 (this may take a while)")
        maybe_git_sync(CVELIST_GIT_URL, cve_root / "cvelistV5")
        entries["cve.cvelistV5"] = str(cve_root / "cvelistV5")

    write_manifest(root, entries)
    print("[sync] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
