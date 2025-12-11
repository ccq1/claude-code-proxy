# LLM Proxy

将本地 LLM 模型适配为 Claude API 格式的代理服务。

## 功能特性

- 🔄 **API 转换**: 将 Claude API 格式转换为本地模型兼容格式
- 🔀 **模型映射**: 自动将 Claude 模型名映射到本地模型
- 🛠️ **工具调用**: 完整支持工具/函数调用
- 📊 **流式响应**: 支持 SSE 流式响应（可配置）
- 🔢 **Token 计数**: 支持自定义 tokenizer 进行准确的 token 计数
- 📝 **事件日志**: 支持批量事件日志记录

## 项目结构

```
llm_proxy/
├── app/
│   ├── __init__.py           # 包初始化
│   ├── main.py               # 主入口文件
│   ├── config.py             # 配置管理
│   ├── constants.py          # 常量定义
│   ├── models/               # 数据模型
│   │   ├── __init__.py
│   │   ├── request.py        # 请求模型
│   │   ├── response.py       # 响应模型
│   │   └── event_logging.py  # 事件日志模型
│   ├── services/             # 服务层
│   │   ├── __init__.py
│   │   ├── model_manager.py  # 模型管理
│   │   ├── converter.py      # 请求/响应转换
│   │   ├── streaming.py      # 流式处理
│   │   └── tokenizer.py      # 分词器管理
│   ├── api/                  # API 路由
│   │   ├── __init__.py
│   │   ├── messages.py       # 消息接口
│   │   ├── tokens.py         # Token 计数接口
│   │   ├── health.py         # 健康检查接口
│   │   └── event_logging.py  # 事件日志接口
│   └── utils/                # 工具模块
│       ├── __init__.py
│       ├── errors.py         # 错误处理
│       └── logging_utils.py  # 日志工具
├── tokenizers/               # Tokenizer 文件
├── logs/                     # 日志目录
├── tests/                    # 测试文件
├── Dockerfile               
├── docker-compose.yml       
├── requirements.txt         
├── env.example              # 环境变量示例
└── README.md
```

## 快速开始

### 1. 使用 Docker (推荐)

```bash
# 复制环境变量配置
cp env.example .env

# 编辑配置文件
vim .env

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 2. 本地运行

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 复制并编辑环境变量
cp env.example .env
vim .env

# 运行服务
python -m app.main

# 或使用 uvicorn (支持热重载)
uvicorn app.main:app --reload --host 0.0.0.0 --port 4000
```

## 配置说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `API_KEY` | `sk-faker` | 本地模型服务的 API Key |
| `BASE_URL` | `http://10.1.1.125:29000/v1` | 本地模型服务 URL |
| `BIG_MODEL` | `qwen3-coder` | 大模型名称 |
| `SMALL_MODEL` | `qwen3-coder` | 小模型名称 |
| `PORT` | `4000` | 服务端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `MAX_TOKENS_LIMIT` | `16384` | 最大输出 token |
| `REQUEST_TIMEOUT` | `90` | 请求超时(秒) |
| `FORCE_DISABLE_STREAMING` | `true` | 强制禁用流式 |

## API 接口

### 消息接口
```
POST /v1/messages
```
兼容 Claude Messages API 格式。

### Token 计数
```
POST /v1/messages/count_tokens
```
计算输入 token 数量。

### 事件日志
```
POST /api/event_logging/batch
```
批量记录事件日志。

### 健康检查
```
GET /health
GET /test-connection
```

## 模型映射

代理服务会自动将 Claude 模型名映射到本地模型：

| Claude 模型 | 映射到 |
|------------|--------|
| `claude-3-opus-*` | `BIG_MODEL` |
| `claude-3-sonnet-*` | `BIG_MODEL` |
| `claude-3-haiku-*` | `SMALL_MODEL` |

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
pytest tests/

# 代码格式化
black app/
isort app/
```

## License

MIT License

