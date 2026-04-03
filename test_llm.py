import json
from openai import OpenAI

client = OpenAI(
    api_key="sk-6f89f05ff97b498490f605d94378322d",
    base_url="http://10.1.1.125:29000/v1"
)

file_path = "20260403_080807_5.json"

with open(file_path, "r", encoding="utf-8") as f:
    full_content = f.read()

total_chars = len(full_content)
total_lines = full_content.count("\n")

print(f"=== 上下文统计 ===")
print(f"文件: {file_path}")
print(f"总行数: {total_lines:,}")
print(f"总字符数: {total_chars:,}")
print(f"总字节数: {len(full_content.encode('utf-8')):,}")
print(f"估算 token 数 (按中英混合 ~2字符/token): {total_chars // 2:,}")
print(f"估算 token 数 (按英文 ~4字符/token): {total_chars // 4:,}")
print()

messages = [
    {"role": "user", "content": full_content + "\n\n请总结上面的对话内容，用一句话描述这个任务的目的。"}
]

print("正在请求模型...")
try:
    response = client.chat.completions.create(
        model="qwen3-coder",
        messages=messages,
    )

    result = response.choices[0].message.content
    usage = response.usage

    print(f"\n=== 模型返回 ===")
    print(f"回复内容: {result}")
    print(f"\n=== Token 使用量 (API 返回) ===")
    if usage:
        print(f"  prompt_tokens:     {usage.prompt_tokens:,}")
        print(f"  completion_tokens: {usage.completion_tokens:,}")
        print(f"  total_tokens:      {usage.total_tokens:,}")
    else:
        print("  (API 未返回 usage 信息)")
except Exception as e:
    print(f"请求失败: {e}")
