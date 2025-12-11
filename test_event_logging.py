"""
测试 event_logging/batch 接口
"""
import httpx
import json

# 测试数据
test_data = {
    "events": [
        {
            "event_type": "ClaudeCodeInternalEvent",
            "event_data": {
                "event_name": "tengu_paste_text",
                "client_timestamp": "2025-12-09T09:55:30.050Z",
                "model": "claude-sonnet-4-5-20250929",
                "session_id": "test-session-123",
                "user_type": "external",
                "env": {
                    "platform": "linux",
                    "version": "2.0.62"
                },
                "device_id": "test-device-id"
            }
        }
    ]
}

def test_api(url: str, api_key: str = None, timeout: float = 30.0):
    """测试 API"""
    print(f"\n{'='*60}")
    print(f"测试 URL: {url}")
    print(f"{'='*60}")
    
    print(f"\n📤 请求内容:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
        print(f"\n🔑 使用 API Key: {api_key[:6]}...")
    
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                url,
                json=test_data,
                headers=headers
            )
            
            print(f"\n📥 响应状态码: {response.status_code}")
            print(f"📥 响应头:")
            for key, value in response.headers.items():
                print(f"   {key}: {value}")
            
            print(f"\n📥 响应内容:")
            try:
                resp_json = response.json()
                print(json.dumps(resp_json, indent=2, ensure_ascii=False))
            except:
                print(response.text[:1000] if response.text else "(空)")
                
    except httpx.TimeoutException:
        print(f"\n❌ 请求超时 (>{timeout}s)")
    except httpx.ConnectError as e:
        print(f"\n❌ 连接失败: {e}")
    except Exception as e:
        print(f"\n❌ 错误: {type(e).__name__}: {e}")


if __name__ == "__main__":
    API_KEY = "123456"
    
    # 测试真实 Anthropic API (本地 8317 端口)
    print("\n" + "="*60)
    print("测试真实 Anthropic API (172.27.180.79:8317)")
    print("="*60)
    test_api("http://172.27.180.79:8317/api/event_logging/batch", api_key=API_KEY, timeout=30.0)
    
    # 测试我们的代理服务 (本地 4000 端口)
    print("\n" + "="*60)
    print("测试我们的代理服务 (172.27.180.79:4000)")
    print("="*60)
    test_api("http://172.27.180.79:4000/api/event_logging/batch", api_key=API_KEY, timeout=10.0)

