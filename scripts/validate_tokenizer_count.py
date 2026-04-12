#!/usr/bin/env python3
"""Validate token counts from a saved prompt snapshot with a lightweight tokenizer."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import litellm
from litellm import create_tokenizer
from tokenizers import Tokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Load a saved prompt snapshot and compare token counts from "
            "tokenizers.Tokenizer and LiteLLM."
        )
    )
    parser.add_argument("snapshot", help="Path to a saved prompt snapshot JSON file.")
    parser.add_argument(
        "--tokenizer-file",
        default="tokenizers/qwen3_5_30b_a3b_tokenizer.json",
        help="Path to a HuggingFace tokenizer.json file.",
    )
    parser.add_argument(
        "--show-role-breakdown",
        action="store_true",
        help="Print token counts for each message role separately.",
    )
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "thinking":
                    parts.append(item.get("thinking", ""))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    return str(content)


def encode_len(tokenizer: Tokenizer, text: str) -> int:
    if not text:
        return 0
    return len(tokenizer.encode(text).ids)


def main() -> int:
    args = parse_args()
    snapshot = load_json(args.snapshot)
    request = snapshot["request"]

    hf_tokenizer = Tokenizer.from_file(args.tokenizer_file)
    litellm_tokenizer = create_tokenizer(Path(args.tokenizer_file).read_text(encoding="utf-8"))

    role_token_counts: dict[str, int] = defaultdict(int)
    role_char_counts: dict[str, int] = defaultdict(int)

    for message in request.get("messages", []) or []:
        role = message.get("role", "unknown")
        text = stringify_content(message.get("content", ""))
        role_char_counts[role] += len(text)
        role_token_counts[role] += encode_len(hf_tokenizer, text)

    tools = request.get("tools", []) or []
    tools_json = json.dumps(tools, ensure_ascii=False, sort_keys=True)
    tools_tokens = encode_len(hf_tokenizer, tools_json)

    direct_messages_tokens = sum(role_token_counts.values())
    direct_total = direct_messages_tokens + tools_tokens

    litellm_messages_only = litellm.token_counter(
        model=request["model"],
        custom_tokenizer=litellm_tokenizer,
        messages=request.get("messages", []),
    )
    litellm_tools_only = litellm.token_counter(
        model=request["model"],
        custom_tokenizer=litellm_tokenizer,
        messages=[],
        tools=tools,
    )
    litellm_total = litellm.token_counter(
        model=request["model"],
        custom_tokenizer=litellm_tokenizer,
        messages=request.get("messages", []),
        tools=tools,
        tool_choice=request.get("tool_choice"),
    )

    print("=== Snapshot ===")
    print(f"file:           {args.snapshot}")
    print(f"model:          {request.get('model')}")
    print(f"messages:       {len(request.get('messages', []) or [])}")
    print(f"tools:          {len(tools)}")
    print()

    if args.show_role_breakdown:
        print("=== Role Breakdown (tokenizers) ===")
        for role in sorted(role_token_counts):
            print(
                f"{role:>10}: tokens={role_token_counts[role]:>6}  "
                f"chars={role_char_counts[role]:>6}"
            )
        print()

    print("=== tokenizers.Tokenizer ===")
    print(f"messages_only:  {direct_messages_tokens}")
    print(f"tools_only:     {tools_tokens}")
    print(f"messages+tools: {direct_total}")
    print()

    print("=== LiteLLM ===")
    print(f"messages_only:  {litellm_messages_only}")
    print(f"tools_only:     {litellm_tools_only}")
    print(f"messages+tools: {litellm_total}")
    print()

    print("=== Delta ===")
    print(f"messages delta: {direct_messages_tokens - litellm_messages_only}")
    print(f"tools delta:    {tools_tokens - litellm_tools_only}")
    print(f"total delta:    {direct_total - litellm_total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
