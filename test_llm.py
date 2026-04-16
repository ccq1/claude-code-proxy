"""
本地 LLM 对话摘要测试脚本（用于读取 JSON 对话文件并请求模型一句话总结）。

本模块故意写得偏长，便于在 IDE 里观察「编辑 / diff」面板的最大可视高度与滚动行为。
下面分段占位，无运行时意义，仅增加行数：

01. 读取 UTF-8 文本文件全文。
02. 统计行数、字符数、字节数。
03. 用简单启发式估算 token（中英混合约 2 字符/token，英文约 4 字符/token）。
04. 构造单轮 user 消息，附加「请总结…」指令。
05. 调用 OpenAI 兼容接口的 chat.completions。
06. 打印模型回复与 usage（若服务端返回）。

07. 环境变量 OPENAI_API_KEY 必填，避免密钥写进仓库。
08. base_url 指向内网网关，可按部署修改。
09. model 名称需与网关路由一致（示例：qwen3-coder）。
10. JSON 文件路径默认为同目录下的示例文件名，可按需修改。

11-20. 占位说明：错误处理仅打印异常字符串；生产环境应记录结构化日志。
21-30. 占位说明：大文件全量读入内存，仅适合离线分析或小文件调试。
31-40. 占位说明：若需流式输出，可改用 stream=True 并迭代 chunk。
41-50. 占位说明：若需多轮对话，应维护 messages 列表并追加 assistant 回复。

51-60. 占位：超时、重试、退避可在客户端层配置。
61-70. 占位：代理与 TLS 校验视内网策略调整。
71-80. 占位：PII 与敏感内容请勿写入日志明文。

81-90. 占位：单元测试可 mock OpenAI client；本脚本为手工联调用途。
91-100. 占位：结束占位块 —— 下方为实际代码。
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


def _require_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("请先设置环境变量 OPENAI_API_KEY")
    return key


def make_client() -> OpenAI:
    return OpenAI(
        api_key=_require_api_key(),
        base_url="http://10.1.1.125:29000/v1",
    )


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def estimate_tokens_mixed_chars(total_chars: int) -> tuple[int, int]:
    approx_cn = max(total_chars // 2, 0)
    approx_en = max(total_chars // 4, 0)
    return approx_cn, approx_en


def print_file_stats(file_path: str, full_content: str) -> None:
    total_chars = len(full_content)
    total_lines = full_content.count("\n")
    byte_len = len(full_content.encode("utf-8"))
    approx_cn, approx_en = estimate_tokens_mixed_chars(total_chars)

    print("=== 上下文统计 ===")
    print(f"文件: {file_path}")
    print(f"总行数: {total_lines:,}")
    print(f"总字符数: {total_chars:,}")
    print(f"总字节数: {byte_len:,}")
    print(f"估算 token 数 (按中英混合 ~2字符/token): {approx_cn:,}")
    print(f"估算 token 数 (按英文 ~4字符/token): {approx_en:,}")
    print()


def build_summary_messages(full_content: str) -> list[dict[str, Any]]:
    prompt_suffix = "\n\n请总结上面的对话内容，用一句话描述这个任务的目的。"
    return [{"role": "user", "content": full_content + prompt_suffix}]


def request_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, Any]],
) -> tuple[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    text = response.choices[0].message.content or ""
    return text, response.usage


def print_model_result(result: str, usage: Any) -> None:
    print("\n=== 模型返回 ===")
    print(f"回复内容: {result}")
    print("\n=== Token 使用量 (API 返回) ===")
    if usage:
        print(f"  prompt_tokens:     {usage.prompt_tokens:,}")
        print(f"  completion_tokens: {usage.completion_tokens:,}")
        print(f"  total_tokens:      {usage.total_tokens:,}")
    else:
        print("  (API 未返回 usage 信息)")


def main() -> None:
    client = make_client()
    file_path = "20260403_080807_5.json"

    full_content = read_text_file(file_path)
    print_file_stats(file_path, full_content)

    messages = build_summary_messages(full_content)
    print("正在请求模型...")
    try:
        result, usage = request_completion(
            client,
            model="qwen3-coder",
            messages=messages,
        )
        print_model_result(result, usage)
    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    main()
