# Agent 项目 Dockerfile

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 先安装核心依赖（利用 Docker 缓存层加速）
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn[standard]>=0.24.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    langchain>=0.1.0 \
    langchain-openai>=0.0.5 \
    langchain-community>=0.0.10 \
    langgraph>=0.0.20 \
    redis>=5.0.0 \
    httpx>=0.25.0 \
    aiohttp>=3.9.0 \
    python-dotenv>=1.0.0 \
    structlog>=23.2.0 \
    tenacity>=8.2.0 \
    PyYAML>=6.0 \
    prometheus-client>=0.19.0 \
    python-jose[cryptography]>=3.3.0 \
    python-multipart>=0.0.6

# 复制源代码
COPY . .

EXPOSE 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
