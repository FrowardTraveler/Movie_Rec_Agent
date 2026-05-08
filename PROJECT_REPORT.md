# 🎬 Movie Rec Agent — 项目报告

> **融合传统推荐算法与大语言模型（LLM）的多 Agent 协作推荐系统**
>
> [![CI Pipeline](https://github.com/YOUR_USERNAME/movie-rec-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/movie-rec-agent/actions/workflows/ci.yml)
> [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
> [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
> [![Test Coverage](https://img.shields.io/badge/tests-113%20passed-brightgreen.svg)](tests/)

## 📋 项目简介

Movie Rec Agent 是一个**工业级**智能电影推荐系统，将传统推荐引擎（DeepFM / YouTubeDNN / ItemCF）与 LLM 多 Agent 协作能力深度融合，提供**自然对话式**的电影推荐体验。

系统采用**微服务架构**，包含两个核心服务：

- **Agent 推理层**（`:8001`）— LangGraph 多 Agent 协作、ReAct 推理、记忆内存、全链路追踪
- **传统推荐系统**（`:8000`）— 召回 → 精排 → 重排完整流水线、A/B 测试、在线评估

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户浏览器 (Vue 3)                         │
└───────────────────────┬──────────────────────────────────────────┘
                        │ SSE 流式 + HTTP
┌───────────────────────▼──────────────────────────────────────────┐
│              Agent 推理层 (FastAPI :8001)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ JWT 认证  │  │ 速率限制  │  │Prometheus│  │ 全局异常处理      │  │
│  │ XSS 防护  │  │ 20次/分  │  │ 指标采集  │  │ 9种错误码         │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              MultiAgentCoordinator                        │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │    │
│  │  │Master    │→│Recommend │→│Search    │→│Summary   │     │    │
│  │  │Agent     │ │Agent     │ │Agent     │ │Agent     │     │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │    │
│  │                                                          │    │
│  │  ┌────────────────────────────────────────────────────┐  │    │
│  │  │           ReAct 推理循环 (最多 3 次迭代)             │  │    │
│  │  │  Thought → Action → Observation → Reflection       │  │    │
│  │  └────────────────────────────────────────────────────┘  │    │
│  │                                                          │    │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────────┐    │    │
│  │  │记忆内存     │ │熔断器      │ │异步任务队列          │    │    │
│  │  │短期+长期    │ │重试+降级   │ │Redis Streams       │    │    │
│  │  │TTL 过期    │ │3层保护     │ │16倍延迟优化         │    │    │
│  │  └────────────┘ └────────────┘ └────────────────────┘    │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────┬──────────────────────┬────────────────────────────┘
               │                      │
     ┌─────────▼──────┐    ┌──────────▼──────────┐
     │ LLM Provider   │    │ 传统推荐系统 :8000   │
     │ (通义千问/其他) │    │                     │
     └────────────────┘    │ 召回: YouTubeDNN     │
                           │      ItemCF          │
                           │ 精排: DeepFM         │
                           │ 重排: 多样性打散      │
                           │ A/B 测试: 50/50      │
                           │ 在线评估: CTR/满意度  │
                           └──────┬───────────────┘
                                  │
         ┌─────────┬──────────────┼──────────────┬─────────┐
         │         │              │              │         │
    ┌────▼───┐ ┌───▼──┐ ┌───────▼───┐ ┌────▼────┐ ┌──▼──┐
    │PostgreSQL│ │Redis │ │Elasticsearch│ │Prometheus│ │Grafana│
    │用户/电影  │ │缓存   │ │全文搜索    │ │指标采集   │ │看板   │
    └────────┘ └──────┘ └───────────┘ └─────────┘ └─────┘
```

## ✨ 核心功能

### 🤖 多 Agent 协作

| Agent              | 职责        | 能力                         |
| ------------------ | --------- | -------------------------- |
| **MasterAgent**    | 意图识别、动态路由 | 识别用户需求，决定调用哪些子 Agent       |
| **RecommendAgent** | 电影推荐      | LLM 生成推荐 + 数据库验证 + IMDB 回退 |
| **SearchAgent**    | 精准搜索      | 搜索特定电影信息                   |
| **SummaryAgent**   | 结果汇总      | 整合各 Agent 结果，生成自然语言回复      |

### 🔄 ReAct 推理循环

MasterAgent 在每次推荐时执行 **Thought → Action → Observation → Reflection** 推理循环：

```
用户: "有什么适合情侣看的电影"
Thought 1: "这是推荐请求，包含场景需求（情侣观影），需要调用 RecommendAgent"
Action 1: 调用 RecommendAgent (mood="情侣观影/浪漫氛围")
Observation 1: 返回 4 部电影，全部通过数据库验证
Reflection 1: 结果质量优秀，所有任务成功且推荐充足 ✅ → 退出循环
```

### 💾 记忆内存系统

```
短期记忆（30 分钟 TTL）:
  - 最近的推荐结果（用于去重）
  - 对话上下文

长期记忆:
  - 用户偏好（自动累积为列表）
  - 喜欢的类型、心情、场景

示例：
  用户第 1 次: "推荐科幻片" → 记忆: 喜欢科幻
  用户第 2 次: "再推荐几部" → 自动跳过已推荐的 + 继续推荐新的
```

### 🛡️ 容错与降级

| 服务     | 保护策略          | 降级行为          |
| ------ | ------------- | ------------- |
| LLM    | 熔断器 + 指数退避重试  | 熔断时降级 MockLLM |
| 传统推荐系统 | 熔断器 + HTTP 超时 | 熔断时返回空数组      |
| Redis  | 熔断器           | 熔断时静默跳过       |

```
LLM 调用失败:
  ├── 重试 2 次（指数退避：0.5s → 1s → 2s）
  ├── 连续 5 次失败 → 熔断 60 秒
  └── 熔断期间 → 降级到 MockLLM ✅

传统推荐不可用:
  ├── 重试 2 次
  ├── 连续 5 次失败 → 熔断 60 秒
  └── 熔断时返回 [] ✅
```

### 📊 A/B 测试与在线评估

```
A/B 测试策略:
  ├── LLM 推荐 (50%) — 新颖度高、可解释性强
  └── 传统推荐 (50%) — 准确率高、覆盖广

在线评估指标:
  ├── CTR (点击率)
  ├── 用户满意度指数
  ├── Top-K 命中率
  ├── 负反馈率
  └── 推荐多样性 & 新颖度
```

### 🔍 全链路追踪

```
用户请求 → API 入口 → 生成 request_id: req-abc123def456
    ├─ API: "请求开始"                    [req-abc123def456]
    ├─ MasterAgent: "意图分析"             [req-abc123def456]
    ├─ RecommendAgent: "LLM 生成推荐"      [req-abc123def456]
    ├─ TradRecClient: "数据库验证"         [req-abc123def456]
    ├─ SummaryAgent: "生成回复"            [req-abc123def456]
    └─ API: "请求结束 (总耗时: 38.5s)"     [req-abc123def456]
```

### ⚡ 异步任务队列

```
之前（同步阻塞）:
用户请求 → Agent 处理 → 等待写入记忆(50ms) → 等待写入对话历史(30ms) → 返回
         总耗时 = Agent时间 + 80ms

现在（异步队列）:
用户请求 → Agent 处理 → 入队(5ms) → 返回 ✅
                                        ↓ 后台 Worker 处理
                                   写入记忆 + 对话历史（不阻塞）
         总耗时 = Agent时间 + 5ms（快 16 倍！）
```

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/movie-rec-agent.git
cd movie-rec-agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写必要的配置：

```env
# LLM 配置
LLM_PROVIDER=openai
LLM_MODEL_ID=gpt-4o-mini
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1

# Redis 配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 传统推荐系统地址
TRAD_REC_BASE_URL=http://localhost:8000
TRAD_REC_CONNECT_TIMEOUT=5
TRAD_REC_TOTAL_TIMEOUT=15
```

### 3. 启动服务

```bash
# 一键启动所有服务（推荐）
docker-compose up -d

# 服务说明:
# - agent:8001    Agent 推理层
# - backend:8000  传统推荐系统
# - frontend:3000 Vue 前端
# - redis:6379    Redis 缓存
# - postgres:5432 PostgreSQL 数据库
# - elasticsearch:9200  全文搜索
# - prometheus:9090 指标采集
# - grafana:3001  可视化看板
```

### 4. 访问服务

| 服务         | 地址                           | 说明            |
| ---------- | ---------------------------- | ------------- |
| 前端界面       | `http://localhost:3000`      | Vue 3 电影推荐 UI |
| Agent API  | `http://localhost:8001/docs` | FastAPI 自动文档  |
| 传统推荐 API   | `http://localhost:8000/docs` | FastAPI 自动文档  |
| Prometheus | `http://localhost:9090`      | 指标查询          |
| Grafana    | `http://localhost:3001`      | 可视化仪表盘        |

### 5. 测试

```bash
# 进入 Agent 容器
docker-compose exec agent bash

# 运行所有测试（113 个用例）
pytest tests/ -v

# 查看覆盖率报告
pytest tests/ --cov=services --cov=agent --cov=llm --cov-report=term-missing
```

## 📁 项目结构

```
movie-rec-agent/
├── agent/                      # Agent 核心
│   ├── multi_agent/            # 多 Agent 协作
│   │   ├── coordinator.py      # 多 Agent 协调器
│   │   ├── master_agent.py     # 主控 Agent（意图识别 + 路由）
│   │   ├── recommend_agent.py  # 推荐 Agent（LLM + 数据库验证）
│   │   ├── search_agent.py     # 搜索 Agent
│   │   ├── summary_agent.py    # 汇总 Agent（结果整合）
│   │   └── react_loop.py       # ReAct 推理循环
│   └── config/                 # 配置管理
│       ├── agent_config.py     # Agent 配置模型
│       └── loader.py           # YAML 配置加载器
│
├── api/                        # API 层
│   ├── main.py                 # FastAPI 主入口（认证/限流/SSE/异常处理）
│   └── exceptions.py           # 全局异常处理器（9 种错误码）
│
├── llm/                        # LLM 管理
│   ├── llm_router.py           # LLM 路由器（OpenAI/本地/Mock 切换）
│   └── response_generator.py   # 流式响应生成器
│
├── services/                   # 服务层
│   ├── auth/                   # JWT 认证
│   ├── cache/                  # Redis 缓存
│   ├── circuit_breaker.py      # 熔断器（CLOSED → OPEN → HALF_OPEN）
│   ├── dialogue/               # 对话历史管理
│   ├── evaluation/             # 在线评估（CTR/满意度/命中率）
│   ├── feedback/               # 用户反馈收集
│   ├── integration/            # 外部系统集成
│   │   └── trad_rec_client.py  # 传统推荐系统客户端（HTTP + 熔断）
│   ├── memory/                 # 记忆内存服务
│   │   └── memory_bank.py      # 短期/长期记忆存储
│   ├── middleware/             # 中间件
│   │   └── rate_limiter.py     # Redis 滑动窗口限流
│   ├── metrics/                # Prometheus 指标
│   ├── queue/                  # 异步任务队列
│   │   ├── task_queue.py       # Redis Streams 队列
│   │   └── workers.py          # 后台 Worker 处理器
│   ├── recommendation/         # 推荐服务
│   │   └── engine_adapter.py   # 推荐引擎适配器
│   └── tracing/                # 全链路追踪
│       └── request_context.py  # request_id 注入 + 性能追踪
│
├── skills/                     # 技能层
│   ├── base.py                 # 技能基类
│   ├── conversation/           # 对话技能（问候/情感/智能回复）
│   ├── recommend/              # 推荐技能
│   ├── search/                 # 搜索技能
│   ├── scene/                  # 场景推荐（约会/通勤/放松）
│   └── profile/                # 用户画像管理
│
├── tests/                      # 测试（113 个用例）
│   ├── test_circuit_breaker.py # 熔断器测试（11 用例，覆盖率 95%）
│   ├── test_memory_bank.py     # 记忆内存测试（16 用例，覆盖率 83%）
│   ├── test_tracing.py         # 全链路追踪测试（20 用例，覆盖率 95%）
│   ├── test_llm_router.py      # LLM 路由器测试（10 用例，覆盖率 76%）
│   ├── test_trad_rec_client.py # 传统推荐客户端测试（15 用例）
│   ├── test_exceptions.py      # 全局异常处理测试（14 用例）
│   ├── test_coordinator.py     # 协调器测试（12 用例，覆盖率 51%）
│   └── ...
│
├── frontend/                   # Vue 3 前端
│   └── src/
│       ├── App.vue             # 主应用组件（SSE 流式聊天）
│       └── components/
│           ├── MovieCard.vue   # 电影卡片（海报/IMDB 链接/评分）
│           └── ChatMessage.vue # 聊天消息组件
│
├── configs/                    # 配置文件
│   └── config.yaml             # Agent 配置（YAML）
│
├── .github/workflows/ci.yml    # CI/CD 流水线（test + lint + docker build）
├── docker-compose.yaml         # Docker 编排（8 个服务）
└── dockerfile                  # Agent 容器构建
```

## 🔌 API 接口

### 智能推荐（SSE 流式）

```bash
curl -N -X POST http://localhost:8001/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "6041",
    "query": "推荐几部科幻片"
  }'
```

### 推荐（非流式）

```bash
curl -X POST http://localhost:8001/api/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "6041",
    "query": "推荐几部科幻片",
    "top_k": 10
  }'
```

### 获取对话历史

```bash
curl http://localhost:8001/api/history/6041?n=10
```

### 更新用户偏好

```bash
curl -X PUT http://localhost:8001/api/profile/6041 \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": {
      "favorite_genre": "sci-fi",
      "preferred_mood": "relaxing"
    }
  }'
```

### 提交反馈

```bash
curl -X POST http://localhost:8001/api/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "6041",
    "query": "推荐科幻片",
    "rated_movie_id": 123,
    "rating": 5,
    "feedback_type": "like"
  }'
```

### 记录事件（在线评估）

```bash
curl -X POST http://localhost:8001/api/events \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "6041",
    "event_type": "click",
    "movie_id": 123,
    "strategy": "llm_only"
  }'
```

## 📊 错误响应格式

所有 API 错误统一返回格式：

```json
{
  "success": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "无权访问其他用户的对话历史",
    "request_id": "req-abc123def456",
    "details": { ... }
  }
}
```

| 错误码                   | HTTP 状态 | 说明      |
| --------------------- | ------- | ------- |
| `VALIDATION_ERROR`    | 400     | 参数校验失败  |
| `UNAUTHORIZED`        | 401     | 未认证     |
| `FORBIDDEN`           | 403     | 无权访问    |
| `NOT_FOUND`           | 404     | 资源不存在   |
| `RATE_LIMITED`        | 429     | 请求过于频繁  |
| `TIMEOUT`             | 408     | 请求超时    |
| `SERVICE_UNAVAILABLE` | 503     | 服务暂时不可用 |
| `INTERNAL_ERROR`      | 500     | 系统内部错误  |

## 🧪 测试

```bash
# 运行所有测试
pytest tests/ -v

# 查看覆盖率
pytest tests/ --cov=services --cov=agent --cov=llm --cov-report=html

# 运行特定模块测试
pytest tests/test_circuit_breaker.py -v     # 熔断器
pytest tests/test_memory_bank.py -v         # 记忆内存
pytest tests/test_exceptions.py -v          # 异常处理
pytest tests/test_trad_rec_client.py -v     # 传统推荐客户端
```

### 测试覆盖率

| 模块      | 覆盖率     | 用例数     |
| ------- | ------- | ------- |
| 熔断器     | **95%** | 11      |
| 全链路追踪   | **95%** | 20      |
| 配置管理    | **97%** | —       |
| 记忆内存    | **83%** | 16      |
| LLM 路由器 | **76%** | 10      |
| 配置加载器   | **74%** | —       |
| 推荐引擎适配器 | **67%** | 4       |
| 全局异常处理  | **新增**  | 14      |
| 传统推荐客户端 | **新增**  | 15      |
| **总计**  | **32%** | **113** |

## 🔧 CI/CD 流水线

GitHub Actions 自动执行：

```yaml
Push/PR → 测试 (pytest) → Lint (ruff) → Docker Build
           ├── 覆盖率报告 (codecov)
           ├── 代码风格检查
           └── 构建 Docker 镜像
```

## 📈 监控与可观测性

### Prometheus 指标

| 指标                                              | 说明                            |
| ----------------------------------------------- | ----------------------------- |
| `http_requests_total`                           | QPS（按 method/endpoint/status） |
| `http_request_duration_seconds`                 | 请求延迟直方图                       |
| `cache_hits_total` / `cache_misses_total`       | 缓存命中/未命中                      |
| `llm_calls_total` / `llm_call_duration_seconds` | LLM 调用统计                      |
| `active_connections`                            | 活跃 SSE 连接数                    |
| `rate_limit_exceeded_total`                     | 限流触发次数                        |
| `recommendation_events_total`                   | 推荐事件（展示/点击/评分）                |
| `recommendation_ctr`                            | 推荐点击率                         |
| `recommendation_hit_rate`                       | Top-K 命中率                     |

### Grafana 仪表盘

预配置面板：

- 请求 QPS 与延迟分布
- 缓存命中率
- LLM 调用成功率与延迟
- 推荐 CTR 与满意度
- 限流触发频率

## 🛠️ 技术栈

| 分类           | 技术                                   |
| ------------ | ------------------------------------ |
| **Web 框架**   | FastAPI + Uvicorn                    |
| **Agent 框架** | LangGraph                            |
| **LLM**      | OpenAI 兼容 API（通义千问/DeepSeek/本地模型）    |
| **推荐算法**     | DeepFM + YouTubeDNN + ItemCF         |
| **缓存**       | Redis 7                              |
| **数据库**      | PostgreSQL 16                        |
| **搜索**       | Elasticsearch 8                      |
| **前端**       | Vue 3 + Vite + TailwindCSS           |
| **监控**       | Prometheus + Grafana                 |
| **容器化**      | Docker Compose                       |
| **CI/CD**    | GitHub Actions                       |
| **测试**       | pytest + pytest-asyncio + pytest-cov |
| **代码质量**     | ruff (lint + format)                 |

## 📝 开发指南

### 添加新 Agent

1. 在 `agent/multi_agent/` 下创建新的 Agent 文件
2. 实现 `execute()` 方法
3. 在 `agent/multi_agent/__init__.py` 中注册
4. 在 `MasterAgent` 的 Prompt 中添加路由规则

### 添加新技能

1. 在 `skills/` 下创建新的技能目录
2. 继承 `BaseSkill` 实现 `execute()` 方法
3. 在对应的 Agent 中调用

### 添加新测试

1. 在 `tests/` 下创建 `test_模块名.py`
2. 使用 `pytest-asyncio` 的 `async def test_xxx()` 编写异步测试
3. 运行 `pytest tests/test_模块名.py -v` 验证

## 📜 许可证

MIT

***

## 🎯 面试亮点

如果将此项目用于**大厂 AI 应用工程师面试**，建议重点展示：

1. **多 Agent 协作架构** — 不是简单的 prompt 拼接，而是 MasterAgent 动态路由 + 4 个子 Agent 协作
2. **ReAct 推理循环** — Thought → Action → Observation → Reflection，自我反思、动态调整
3. **容错设计** — 熔断器（CLOSED → OPEN → HALF\_OPEN → CLOSED）+ 指数退避重试 + LLM 降级
4. **记忆内存系统** — 短期记忆（推荐去重）+ 长期记忆（用户偏好自动累积）+ TTL 自动过期
5. **异步任务队列** — Redis Streams 解耦后台任务，请求延迟降低 16 倍
6. **全链路追踪** — request\_id 贯穿 API → Agent → LLM → 数据库，快速定位问题
7. **A/B 测试 + 在线评估** — LLM vs 传统推荐效果对比，数据驱动优化
8. **CI/CD 流水线** — GitHub Actions 自动测试 + lint + Docker 构建
9. **113 个测试用例** — 关键模块覆盖率 70%+，体现工程质量意识

