#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

import yaml


REQUEST_LINE_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)\s+HTTP/\d\.\d$", re.I)


def discover_request_file(workdir: Path) -> Path | None:
    patterns = ("*.http", "request*", "poc*", "exploit*")
    for pattern in patterns:
        for path in sorted(workdir.glob(pattern)):
            if path.is_file():
                return path
    return None


def parse_http_request(text: str) -> dict[str, object]:
    lines = [line.rstrip("\r") for line in text.splitlines()]
    method = "GET"
    path = "/"
    headers: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not in_body:
            req_match = REQUEST_LINE_RE.match(line.strip())
            if req_match:
                method = req_match.group(1).upper()
                path = req_match.group(2)
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

    host = headers.get("Host", "{{TARGET_HOST}}")
    scheme = "https" if headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
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
        "User-Agent: PandoraQ-POC-Validator/1.0\n"
        "Connection: close\n\n"
        "# safety: read-only verification request\n"
    )


def build_python_scaffold(parsed: dict[str, object]) -> str:
    method = str(parsed["method"]).upper()
    path = str(parsed["path"])
    scheme = str(parsed["scheme"])
    host = str(parsed["host"])
    body = str(parsed["body"])
    headers = {k: v for k, v in dict(parsed["headers"]).items() if k.lower() not in {"host", "content-length", "connection"}}

    return (
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n\n"
        "import requests\n\n"
        f"TARGET = \"{scheme}://{host}\"\n"
        f"PATH = \"{path}\"\n"
        f"METHOD = \"{method}\"\n"
        f"HEADERS = {json.dumps(headers, ensure_ascii=False, indent=2)}\n"
        f"BODY = {json.dumps(body)}\n\n"
        "def main() -> int:\n"
        "    url = TARGET.rstrip('/') + PATH\n"
        "    response = requests.request(METHOD, url, headers=HEADERS, data=BODY, timeout=15, allow_redirects=False)\n"
        "    print(f\"status={response.status_code}\")\n"
        "    # proof signal: tune these matchers before batch use\n"
        "    if response.status_code in (200, 401, 403):\n"
        "        print(\"verification: signal observed\")\n"
        "        return 0\n"
        "    print(\"verification: no strong signal\")\n"
        "    return 1\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main())\n"
    )


def build_nuclei_template(parsed: dict[str, object], name: str) -> str:
    method = str(parsed["method"]).upper()
    path = str(parsed["path"])
    body = str(parsed["body"])
    body_block = f"\n    body: |\n      {body.replace(chr(10), chr(10) + '      ')}" if body else ""
    return (
        "id: " + name + "-safe-verify\n"
        "info:\n"
        "  name: " + name + " safe verification\n"
        "  author: pandoraq\n"
        "  severity: medium\n"
        "  description: Auto-generated safe verification template\n"
        "requests:\n"
        "  - method: " + method + "\n"
        "    path:\n"
        "      - \"{{BaseURL}}" + path + "\"\n"
        + body_block
        + "\n"
        "    matchers-condition: and\n"
        "    matchers:\n"
        "      - type: status\n"
        "        status:\n"
        "          - 200\n"
        "          - 401\n"
        "          - 403\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold production-friendly POC verification artifacts from a raw request sample.")
    parser.add_argument("--workdir", default=".", help="Directory containing request samples.")
    parser.add_argument("--request-file", default="", help="Explicit HTTP request sample file.")
    parser.add_argument("--name", default="target", help="POC name prefix.")
    parser.add_argument("--output-dir", default="generated_poc_pack", help="Output directory.")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    request_file = Path(args.request_file).expanduser().resolve() if args.request_file else discover_request_file(workdir)
    if not request_file or not request_file.exists():
        raise SystemExit("No request sample found. Provide --request-file or add *.http / request* file.")

    raw = request_file.read_text(encoding="utf-8", errors="ignore")
    parsed = parse_http_request(raw)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    http_template = build_http_template(parsed)
    py_scaffold = build_python_scaffold(parsed)
    nuclei_template = build_nuclei_template(parsed, args.name)

    http_path = output_dir / f"{args.name}_verify.http"
    py_path = output_dir / f"{args.name}_verify.py"
    nuclei_path = output_dir / f"{args.name}_safe.yaml"

    http_path.write_text(http_template, encoding="utf-8")
    py_path.write_text(py_scaffold, encoding="utf-8")
    nuclei_path.write_text(nuclei_template, encoding="utf-8")

    # quick self-checks
    ast.parse(py_scaffold)
    yaml.safe_load(nuclei_template)

    manifest = {
        "requestFile": str(request_file),
        "parsedRequest": parsed,
        "artifacts": [str(http_path), str(py_path), str(nuclei_path)],
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
