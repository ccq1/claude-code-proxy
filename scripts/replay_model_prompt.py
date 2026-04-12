#!/usr/bin/env python3
"""Replay a saved model prompt snapshot against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a saved prompt snapshot to an OpenAI-compatible "
            "chat completions endpoint and print the returned token usage."
        )
    )
    parser.add_argument(
        "snapshot",
        help="Path to the saved prompt snapshot JSON file.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL", "http://10.1.1.125:29000/v1"),
        help="OpenAI-compatible base URL. Defaults to BASE_URL from .env.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("API_KEY", "sk-faker"),
        help="API key for the upstream endpoint. Defaults to API_KEY from .env.",
    )
    parser.add_argument(
        "--mode",
        choices=["nonstream", "stream", "both"],
        default="nonstream",
        help="Request mode. Defaults to nonstream for the most reliable usage output.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Request timeout in seconds. Defaults to 180.",
    )
    parser.add_argument(
        "--show-request",
        action="store_true",
        help="Print the normalized request body before sending it.",
    )
    return parser.parse_args()


def load_snapshot(snapshot_path: str) -> dict[str, Any]:
    path = Path(snapshot_path)
    if not path.exists():
        raise FileNotFoundError(f"Snapshot file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_request(snapshot: dict[str, Any], *, stream: bool) -> dict[str, Any]:
    request_body = deepcopy(snapshot["request"])
    request_body.pop("api_key", None)
    request_body.pop("base_url", None)

    model = request_body.get("model", "")
    if isinstance(model, str) and model.startswith("openai/"):
        request_body["model"] = model.split("/", 1)[1]

    extra_body = request_body.pop("extra_body", None)
    if isinstance(extra_body, dict):
        for key, value in extra_body.items():
            request_body.setdefault(key, value)

    request_body["stream"] = stream
    if stream:
        request_body.setdefault("stream_options", {"include_usage": True})
    else:
        request_body.pop("stream_options", None)

    return request_body


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def summarize_request(request_body: dict[str, Any]) -> None:
    message_count = len(request_body.get("messages", []) or [])
    tool_count = len(request_body.get("tools", []) or [])
    print("=== Request Summary ===")
    print(f"model:        {request_body.get('model')}")
    print(f"stream:       {request_body.get('stream')}")
    print(f"messages:     {message_count}")
    print(f"tools:        {tool_count}")
    print(f"max_tokens:   {request_body.get('max_tokens')}")
    print(f"temperature:  {request_body.get('temperature')}")
    print()


def print_usage(usage: dict[str, Any] | None) -> None:
    print("=== Usage ===")
    if not usage:
        print("usage: <missing>")
        print()
        return

    print(f"prompt_tokens:     {usage.get('prompt_tokens')}")
    print(f"completion_tokens: {usage.get('completion_tokens')}")
    print(f"total_tokens:      {usage.get('total_tokens')}")
    print()


def print_message_preview(payload: dict[str, Any]) -> None:
    choices = payload.get("choices", []) or []
    if not choices:
        return

    message = choices[0].get("message", {}) or {}
    content = message.get("content")
    reasoning = message.get("reasoning_content")

    print("=== Response Preview ===")
    if reasoning:
        preview = reasoning[:400]
        print(f"reasoning_content: {preview}")
    if content:
        preview = content[:800]
        print(f"content:           {preview}")
    print()


def run_nonstream(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    request_body: dict[str, Any],
) -> None:
    response = client.post(url, headers=headers, json=request_body)
    response.raise_for_status()
    payload = response.json()

    print("=== Non-Stream Response ===")
    print(f"status_code: {response.status_code}")
    print_usage(payload.get("usage"))
    print_message_preview(payload)


def run_stream(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    request_body: dict[str, Any],
) -> None:
    chunk_count = 0
    final_usage: dict[str, Any] | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []

    with client.stream("POST", url, headers=headers, json=request_body) as response:
        response.raise_for_status()

        for raw_line in response.iter_lines():
            if not raw_line:
                continue

            line = raw_line.strip()
            if not line.startswith("data:"):
                continue

            data = line[5:].strip()
            if data == "[DONE]":
                break

            payload = json.loads(data)
            chunk_count += 1

            usage = payload.get("usage")
            if usage is not None:
                final_usage = usage

            choices = payload.get("choices", []) or []
            if not choices:
                continue

            delta = choices[0].get("delta", {}) or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])

    print("=== Stream Response ===")
    print(f"chunk_count: {chunk_count}")
    print_usage(final_usage)

    if reasoning_parts or content_parts:
        preview_payload = {
            "choices": [
                {
                    "message": {
                        "reasoning_content": "".join(reasoning_parts),
                        "content": "".join(content_parts),
                    }
                }
            ]
        }
        print_message_preview(preview_payload)


def main() -> int:
    load_dotenv()
    args = parse_args()

    snapshot = load_snapshot(args.snapshot)
    request_url = args.base_url.rstrip("/") + "/chat/completions"
    headers = build_headers(args.api_key)

    with httpx.Client(timeout=args.timeout) as client:
        if args.mode in {"nonstream", "both"}:
            request_body = normalize_request(snapshot, stream=False)
            summarize_request(request_body)
            if args.show_request:
                print(json.dumps(request_body, ensure_ascii=False, indent=2))
                print()
            run_nonstream(client, request_url, headers, request_body)

        if args.mode == "both":
            print("=" * 80)

        if args.mode in {"stream", "both"}:
            request_body = normalize_request(snapshot, stream=True)
            summarize_request(request_body)
            if args.show_request:
                print(json.dumps(request_body, ensure_ascii=False, indent=2))
                print()
            run_stream(client, request_url, headers, request_body)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPStatusError as exc:
        print(f"HTTP error: {exc.response.status_code} {exc.response.text}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
