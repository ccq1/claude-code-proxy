"""
LLM Proxy 主入口文件
"""
import sys
import socket
import uvicorn
import litellm
from fastapi import FastAPI, Request

from app import __version__
from app.config import config
from app.api import api_router
from app.utils.logging_utils import setup_logging

# 配置 LiteLLM
litellm.drop_params = True
litellm.set_verbose = False
litellm.request_timeout = config.request_timeout
litellm.num_retries = config.max_retries

# 设置日志
logger = setup_logging()

# 创建 FastAPI 应用
app = FastAPI(
    title="LLM Proxy - Local Model to Claude API",
    version=__version__,
    description="将本地 LLM 模型适配为 Claude API 格式的代理服务"
)

# 注册路由
app.include_router(api_router)


# 请求中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    method = request.method
    path = request.url.path
    logger.debug(f"Request: {method} {path}")
    response = await call_next(request)
    return response


def validate_startup() -> bool:
    """验证启动配置"""
    return config.validate_api_key()


def main():
    """主函数"""
    if not validate_startup():
        sys.exit(1)

    # 启动服务器
    if config.workers > 1:
        # 多 worker 模式需要使用字符串形式的 app
        uvicorn.run(
            "main:app",
            host=config.host,
            port=config.port,
            workers=config.workers,
            log_level=config.log_level.lower()
        )
    else:
        uvicorn.run(
            app, 
            host=config.host, 
            port=config.port, 
            log_level=config.log_level.lower()
        )


if __name__ == "__main__":
    main()
