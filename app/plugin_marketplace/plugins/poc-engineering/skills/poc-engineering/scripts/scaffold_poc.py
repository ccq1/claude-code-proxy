#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml


REQUEST_LINE_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)\s+HTTP/\d\.\d$", re.I)


def _depth_within(root: Path, candidate: Path, max_depth: int) -> bool:
    try:
        rel = candidate.relative_to(root)
    except ValueError:
        return False
    return len(rel.parts) <= max_depth


def _looks_like_request_sample(path: Path) -> bool:
    try:
        snippet = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return False

    lines = [line.strip() for line in snippet.splitlines()[:30] if line.strip()]
    if any(REQUEST_LINE_RE.match(line) for line in lines):
        return True
    headers = ("host:", "user-agent:", "content-type:", "authorization:")
    return any(line.lower().startswith(headers) for line in lines)


def discover_request_file(workdir: Path, max_depth: int = 4) -> Path | None:
    patterns = ("*.http", "*.txt", "request*", "poc*", "exploit*")
    candidates: list[Path] = []

    for pattern in patterns:
        for path in workdir.rglob(pattern):
            if not path.is_file() or not _depth_within(workdir, path, max_depth):
                continue
            if _looks_like_request_sample(path):
                candidates.append(path)

    if not candidates:
        return None

    def rank(path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        score = 0
        if name.endswith(".http"):
            score += 4
        if "request" in name:
            score += 3
        if "poc" in name:
            score += 2
        if "exploit" in name:
            score += 1
        return (-score, len(path.parts), str(path))

    return sorted(candidates, key=rank)[0]


def _parse_scheme_host_path(raw_target: str, headers: dict[str, str]) -> tuple[str, str, str]:
    if raw_target.startswith(("http://", "https://")):
        parsed = urlparse(raw_target)
        scheme = parsed.scheme
        host = parsed.netloc or headers.get("Host", "{{TARGET_HOST}}")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        return scheme, host, path

    host = headers.get("Host", "{{TARGET_HOST}}")
    host_lower = host.lower()
    scheme = "https" if any(host_lower.endswith(f":{p}") for p in ("443", "8443", "9443")) else "http"
    return scheme, host, raw_target


def parse_http_request(text: str) -> dict[str, object]:
    lines = [line.rstrip("\r") for line in text.splitlines()]
    method = "GET"
    raw_target = "/"
    headers: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not in_body:
            req_match = REQUEST_LINE_RE.match(line.strip())
            if req_match:
                method = req_match.group(1).upper()
                raw_target = req_match.group(2)
                continue
            if not line.strip():
                in_body = True
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
                continue
        else:
            body_lines.append(line)

    scheme, host, path = _parse_scheme_host_path(raw_target, headers)
    body = "\n".join(body_lines).strip()

    return {
        "method": method,
        "path": path,
        "headers": headers,
        "host": host,
        "scheme": scheme,
        "body": body,
    }


def build_http_template(parsed: dict[str, object]) -> str:
    method = str(parsed["method"])
    path = str(parsed["path"])
    host = str(parsed["host"])
    return (
        f"{method} {path} HTTP/1.1\n"
        f"Host: {host}\n"
        "User-Agent: PandoraQ-POC-Validator/1.1\n"
        "Connection: close\n"
        "# Authorization: Bearer {{TOKEN}}\n\n"
        "# safety: read-only verification request\n"
    )


def build_python_scaffold(parsed: dict[str, object], success_statuses: list[int], signal_statuses: list[int], success_keyword: str) -> str:
    method = str(parsed["method"]).upper()
    path = str(parsed["path"])
    scheme = str(parsed["scheme"])
    host = str(parsed["host"])
    body = str(parsed["body"])
    headers = {k: v for k, v in dict(parsed["headers"]).items() if k.lower() not in {"host", "content-length", "connection"}}

    return (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n\n"
        "import argparse\n"
        "import requests\n\n"
        f"DEFAULT_TARGET = \"{scheme}://{host}\"\n"
        f"PATH = \"{path}\"\n"
        f"METHOD = \"{method}\"\n"
        f"HEADERS = {json.dumps(headers, ensure_ascii=False, indent=2)}\n"
        f"BODY = {json.dumps(body)}\n"
        f"SUCCESS_STATUSES = {success_statuses}\n"
        f"SIGNAL_STATUSES = {signal_statuses}\n"
        f"SUCCESS_KEYWORD = {json.dumps(success_keyword)}\n\n"
        "def main() -> int:\n"
        "    parser = argparse.ArgumentParser(description=\"Safe verification scaffold\")\n"
        "    parser.add_argument(\"--target\", default=DEFAULT_TARGET, help=\"Base URL, e.g. https://target:8443\")\n"
        "    parser.add_argument(\"--timeout\", type=int, default=15)\n"
        "    args = parser.parse_args()\n\n"
        "    url = args.target.rstrip('/') + PATH\n"
        "    response = requests.request(METHOD, url, headers=HEADERS, data=BODY, timeout=args.timeout, allow_redirects=False)\n"
        "    print(f\"status={response.status_code}\")\n"
        "    body_text = response.text or \"\"\n"
        "    has_keyword = bool(SUCCESS_KEYWORD) and (SUCCESS_KEYWORD in body_text)\n\n"
        "    if response.status_code in SUCCESS_STATUSES or has_keyword:\n"
        "        print(\"verification: strong signal observed\")\n"
        "        return 0\n"
        "    if response.status_code in SIGNAL_STATUSES:\n"
        "        print(\"verification: weak signal observed (auth/prerequisite may be missing)\")\n"
        "        return 2\n"
        "    print(\"verification: no signal\")\n"
        "    return 1\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n"
    )


def build_nuclei_template(parsed: dict[str, object], name: str, success_statuses: list[int], success_keyword: str) -> str:
    method = str(parsed["method"]).upper()
    path = str(parsed["path"])
    body = str(parsed["body"])
    body_block = f"\n    body: |\n      {body.replace(chr(10), chr(10) + '      ')}" if body else ""
    matcher_lines = [
        "    matchers-condition: and",
        "    matchers:",
        "      - type: status",
        "        status:",
    ]
    for code in success_statuses:
        matcher_lines.append(f"          - {code}")

    if success_keyword:
        matcher_lines.extend(
            [
                "      - type: word",
                "        part: body",
                "        words:",
                f"          - {json.dumps(success_keyword)}",
            ]
        )

    matchers = "\n".join(matcher_lines)

    return (
        "id: " + name + "-safe-verify\n"
        "info:\n"
        "  name: " + name + " safe verification\n"
        "  author: pandoraq\n"
        "  severity: low\n"
        "  description: Auto-generated safe verification template\n"
        "requests:\n"
        "  - method: " + method + "\n"
        "    path:\n"
        "      - \"{{BaseURL}}" + path + "\"\n"
        + body_block
        + "\n"
        + matchers
        + "\n"
    )


def parse_statuses(value: str) -> list[int]:
    results: list[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        code = int(raw)
        if code < 100 or code > 599:
            raise ValueError(f"Invalid HTTP status code: {raw}")
        results.append(code)
    if not results:
        raise ValueError("At least one status code is required")
    return sorted(set(results))


def resolve_profile(profile: str) -> tuple[str, str, str]:
    presets = {
        "safe": ("200", "401,403", ""),
        "balanced": ("200,204", "401,403", "success"),
        "aggressive": ("200,201,202,204", "400,401,403,405", ""),
    }
    if profile not in presets:
        raise ValueError(f"Unknown profile: {profile}")
    return presets[profile]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold production-friendly POC verification artifacts from a raw request sample.")
    parser.add_argument("--workdir", default=".", help="Directory containing request samples.")
    parser.add_argument("--request-file", default="", help="Explicit HTTP request sample file.")
    parser.add_argument("--name", default="target", help="POC name prefix.")
    parser.add_argument("--output-dir", default="generated_poc_pack", help="Output directory.")
    parser.add_argument("--max-depth", type=int, default=4, help="Max recursion depth when auto-discovering request samples.")
    parser.add_argument("--profile", default=None, choices=["safe", "balanced", "aggressive"], help="Preset verification profile.")
    parser.add_argument("--success-status", default="200", help="Comma-separated strong-signal status codes.")
    parser.add_argument("--signal-status", default="401,403", help="Comma-separated weak-signal status codes.")
    parser.add_argument("--success-keyword", default="", help="Optional keyword expected in response body for stronger confidence.")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    output_dir = (workdir / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir).resolve()

    request_file = Path(args.request_file).expanduser().resolve() if args.request_file else discover_request_file(workdir, max_depth=args.max_depth)
    if not request_file or not request_file.exists():
        raise SystemExit("No request sample found. Provide --request-file or add *.http / request* file.")

    success_status_raw = args.success_status
    signal_status_raw = args.signal_status
    success_keyword = args.success_keyword
    if args.profile:
        success_status_raw, signal_status_raw, profile_keyword = resolve_profile(args.profile)
        if not args.success_keyword:
            success_keyword = profile_keyword

    success_statuses = parse_statuses(success_status_raw)
    signal_statuses = parse_statuses(signal_status_raw)

    raw = request_file.read_text(encoding="utf-8", errors="ignore")
    parsed = parse_http_request(raw)

    output_dir.mkdir(parents=True, exist_ok=True)

    http_template = build_http_template(parsed)
    py_scaffold = build_python_scaffold(parsed, success_statuses, signal_statuses, success_keyword)
    nuclei_template = build_nuclei_template(parsed, args.name, success_statuses, success_keyword)

    http_path = output_dir / f"{args.name}_verify.http"
    py_path = output_dir / f"{args.name}_verify.py"
    nuclei_path = output_dir / f"{args.name}_safe.yaml"

    http_path.write_text(http_template, encoding="utf-8")
    py_path.write_text(py_scaffold, encoding="utf-8")
    nuclei_path.write_text(nuclei_template, encoding="utf-8")

    ast.parse(py_scaffold)
    yaml.safe_load(nuclei_template)

    manifest = {
        "requestFile": str(request_file),
        "parsedRequest": parsed,
        "artifacts": [str(http_path), str(py_path), str(nuclei_path)],
        "verificationCriteria": {
            "successStatus": success_statuses,
            "signalStatus": signal_statuses,
            "successKeyword": success_keyword,
            "profile": args.profile or "custom",
        },
        "safetyMode": "read-only verification",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Generated: {http_path}")
    print(f"Generated: {py_path}")
    print(f"Generated: {nuclei_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
