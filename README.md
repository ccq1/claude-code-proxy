# LLM Proxy

将本地 LLM 模型适配为 Claude API 格式的代理服务。

## 功能特性

- 🔄 **API 转换**: 将 Claude API 格式转换为本地模型兼容格式
- 🔀 **模型映射**: 自动将 Claude 模型名映射到本地模型
- 🛠️ **工具调用**: 完整支持工具/函数调用
- 📊 **流式响应**: 支持 SSE 流式响应（可配置）
- 🔢 **Token 计数**: 支持自定义 tokenizer 进行准确的 token 计数
- 📝 **事件日志**: 支持批量事件日志记录
- 🔐 **双层认证**: 平台主身份 + 本地注册登录次身份
- 🐳 **Docker 优化**: 使用国内镜像源加速构建，支持宿主机网络模式
- ⚡ **高性能**: 支持多 worker 部署和健康检查

## 项目结构

```
llm_proxy/
├── app/
│   ├── __init__.py           # 包初始化
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
├── main.py                   # 主入口文件
├── Dockerfile               # Docker 镜像配置
├── docker-compose.yml       # Docker Compose 配置
├── .dockerignore           # Docker 忽略文件
├── requirements.txt         # Python 依赖
└── README.md               # 项目文档
```

## 快速开始

### 1. 使用 Docker (推荐)

#### 构建镜像
```bash
# 克隆项目
git clone <repository-url>
cd llm_proxy

# 构建镜像（使用国内镜像源加速）
docker build -t llm-proxy:latest .
```

#### 使用 Docker Compose 启动
```bash
# 启动服务（使用宿主机网络模式）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

#### 直接运行容器
```bash
# 使用宿主机网络模式（推荐）
docker run -d \
  --name llm-proxy \
  --network host \
  -e MODEL_COUNT=2 \
  -e DEFAULT_TOKENIZER_FILE=tokenizers/qwen3_5_30b_a3b_tokenizer.json \
  -e MODEL_NAME_1=qwen3-35b \
  -e MODEL_BASE_URL_1=http://10.1.1.125:29000/v1 \
  -e MODEL_AUTH_TOKEN_1=sk-qwen \
  -e MODEL_TOKENIZER_FILE_1=tokenizers/qwen3_5_30b_a3b_tokenizer.json \
  -e MODEL_NAME_2=glm-5.1 \
  -e MODEL_BASE_URL_2=http://10.1.1.125:29001/v1 \
  -e MODEL_AUTH_TOKEN_2=sk-glm \
  -e HOST=0.0.0.0 \
  -e PORT=4000 \
  llm-proxy:latest
```

### 2. 本地运行

```bash
# 克隆项目
git clone <repository-url>
cd llm_proxy

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖（使用国内源）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 运行服务
python main.py

# 或使用 uvicorn (支持热重载)
uvicorn main:app --reload --host 0.0.0.0 --port 4000
```

## Docker 优化特性

### 构建优化
- **国内镜像源**: 使用清华大学镜像源加速 apt 包安装
- **PyPI 加速**: 默认使用清华大学 PyPI 源
- **缓存优化**: 合理利用 Docker 层缓存
- **健康检查**: 内置健康检查机制

### 网络模式
- **Host 网络模式**: 直接使用宿主机网络，提供最佳性能
- **端口直通**: 容器直接监听宿主机端口，无需端口映射
- **服务发现**: 可直接访问宿主机上的其他服务

## 配置说明

### 环境变量

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MODEL_COUNT` | `0` | 模型数量，必须大于 0 |
| `DEFAULT_TOKENIZER_FILE` | `tokenizers/qwen3_5_30b_a3b_tokenizer.json` | 默认 tokenizer 文件，未传模型专属 tokenizer 时使用 |
| `MODEL_NAME_<N>` | `` | 第 N 个模型的前端模型名 |
| `MODEL_BASE_URL_<N>` | `` | 第 N 个模型请求转发地址 |
| `MODEL_AUTH_TOKEN_<N>` | `` | 第 N 个模型鉴权 token |
| `MODEL_TOKENIZER_FILE_<N>` | 可选 | 第 N 个模型对应 tokenizer 文件，不传则回退到 `DEFAULT_TOKENIZER_FILE` |
| `HOST` | `0.0.0.0` | 服务监听地址 |
| `PORT` | `4000` | 服务端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `MAX_TOKENS_LIMIT` | `16384` | 最大输出 token 数 |
| `REQUEST_TIMEOUT` | `90` | 请求超时时间(秒) |
| `MAX_RETRIES` | `1` | 最大重试次数 |
| `WORKERS` | `4` | 工作进程数 |
| `AUTH_DB_PATH` | `data/auth.db` | 本地认证 SQLite 文件路径 |
| `AUTH_SESSION_TTL_SECONDS` | `2592000` | 本地登录会话有效期（秒） |
| `PLATFORM_AUTH_ENABLED` | `true` | 是否启用平台身份识别 |
| `PLATFORM_AUTH_PRECEDENCE` | `true` | 平台身份是否优先于本地身份 |
| `PLATFORM_IDENTITY_TOKEN_ENV` | `PLATFORM_USER_TOKEN` | 平台 token 所在环境变量名 |
| `PLATFORM_IDENTITY_USER_ID_ENV` | `PLATFORM_USER_ID` | 平台用户 ID 环境变量名 |
| `PLATFORM_IDENTITY_NAME_ENV` | `PLATFORM_USER_NAME` | 平台用户名环境变量名 |
| `PLATFORM_IDENTITY_EMAIL_ENV` | `PLATFORM_USER_EMAIL` | 平台邮箱环境变量名 |
### 多模型路由示例

当你希望前端传不同的 `model`，后端自动切到不同模型地址时，可以配置编号式 key-value 形式：

```bash
export MODEL_COUNT=2
export DEFAULT_TOKENIZER_FILE=tokenizers/qwen3_5_30b_a3b_tokenizer.json
export MODEL_NAME_1=qwen3-35b
export MODEL_BASE_URL_1=http://10.1.1.125:29000/v1
export MODEL_AUTH_TOKEN_1=sk-qwen
export MODEL_TOKENIZER_FILE_1=tokenizers/qwen3_5_30b_a3b_tokenizer.json
export MODEL_NAME_2=glm-5.1
export MODEL_BASE_URL_2=http://10.1.1.125:29001/v1
export MODEL_AUTH_TOKEN_2=sk-glm
# MODEL_TOKENIZER_FILE_2 可不传，此时默认使用 qwen3_5_30b_a3b_tokenizer.json
```

请求进入后会按前端传入的 `model` 精确匹配对应路由，并选择对应的 tokenizer 单例来计算 token。只有 `MODEL_COUNT` 范围内明确配置过的模型才允许请求。

### 流式响应配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `FORCE_DISABLE_STREAMING` | `true` | 强制禁用流式响应 |
| `EMERGENCY_DISABLE_STREAMING` | `false` | 紧急禁用流式响应 |
| `MAX_STREAMING_RETRIES` | `12` | 流式响应最大重试次数 |

## API 接口

### 消息接口
```http
POST /v1/messages
```
兼容 Claude Messages API 格式，支持：
- 普通文本对话
- 工具/函数调用
- 流式响应
- 系统提示词

### Token 计数
```http
POST /v1/messages/count_tokens
```
计算输入消息的准确 token 数量。

### 事件日志
```http
POST /api/event_logging/batch
```
批量记录事件日志，支持 Claude 事件日志格式。

### 认证接口（新增）
```http
GET  /auth/me
POST /auth/register
POST /auth/login
POST /auth/logout
```

- 平台身份（环境变量注入）会自动创建影子账户（provider=platform）。
- 本地账号通过 `register/login` 管理，返回 `session_token`（Bearer）。
- 当 `PLATFORM_AUTH_PRECEDENCE=true` 且平台身份可用时，`/auth/me` 以平台身份为有效身份返回。

### 健康检查
```http
GET /health
GET /test-connection
```
检查服务状态和后端连接。

## 模型映射

代理服务会自动将 Claude 模型名映射到本地模型：

| Claude 模型 | 映射到 |
|------------|--------|
| `claude-3-opus-*` | `BIG_MODEL` |
| `claude-3-sonnet-*` | `BIG_MODEL` |
| `claude-3-haiku-*` | `SMALL_MODEL` |

## 性能优化

### Docker 部署建议
1. **使用 Host 网络模式**: 提供最佳网络性能
2. **多 Worker 部署**: 根据 CPU 核心数调整 `WORKERS` 环境变量
3. **资源限制**: 在生产环境中设置适当的内存和 CPU 限制

### 本地部署建议
1. **Python 版本**: 推荐 Python 3.11+
2. **依赖管理**: 使用虚拟环境隔离依赖
3. **日志配置**: 在生产环境中将日志级别设置为 INFO 或 WARNING

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 运行测试（如果有）
# pytest tests/

# 代码格式化
# black app/
# isort app/
```

## 故障排除

### 常见问题

1. **构建慢**: 已使用国内镜像源，构建应该很快完成
2. **网络连接**: 使用 Host 网络模式时，确保端口 4000 未被占用
3. **后端连接**: 检查 `BASE_URL` 配置和后端服务状态
4. **内存不足**: 调整 `WORKERS` 数量或增加容器内存限制

### 日志查看
```bash
# Docker Compose
docker-compose logs -f llm-proxy

# 直接运行 Docker
docker logs -f llm-proxy

# 本地运行
# 日志输出到控制台和 logs/ 目录
```

## License

MIT License
