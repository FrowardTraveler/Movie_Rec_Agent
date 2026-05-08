# Movie Rec Agent

智能电影推荐 Agent - 基于 LLM + LangGraph + RAG + 推荐算法

[![CI Pipeline](https://github.com/YOUR_USERNAME/movie-rec-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/movie-rec-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 项目简介

这是一个工业级的智能电影推荐系统，融合了传统推荐算法和 LLM 能力，提供自然对话式的电影推荐体验。

### MVP 版本功能

- 基于 LangGraph 的 Agent 推理流程
- 对话技能 (闲聊、情感回应)
- 推荐技能 (调用推荐引擎)
- Redis 缓存支持
- FastAPI REST 接口

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 安装依赖
pip install -e .
```

### 2. 配置

复制环境变量示例文件并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写必要的配置。

### 3. 启动服务

```bash
# 启动开发服务器
python main.py

# 或者使用 uvicorn
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后访问：

- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

### 4. 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试
pytest tests/test_engine_adapter.py -v
pytest tests/test_conversation_skill.py -v
```

## 项目结构

```
movie-rec-agent/
├── agent/                  # Agent 核心
│   ├── agent.py           # LangGraph Agent 实现
│   └── config/            # 配置管理
├── skills/                 # 技能层
│   ├── base.py            # 技能基类
│   ├── conversation/      # 对话技能
│   └── recommend/         # 推荐技能
├── tools/                  # 工具层
│   ├── recommend_tools.py # 推荐工具
│   └── search_tools.py    # 搜索工具
├── services/               # 服务层
│   ├── recommendation/    # 推荐服务
│   └── cache/             # 缓存服务
├── llm/                    # LLM 管理
│   └── llm_router.py      # LLM 路由器
├── api/                    # API 层
│   └── main.py            # FastAPI 主入口
├── tests/                  # 测试
├── configs/                # 配置文件
├── main.py                 # 启动脚本
└── pyproject.toml          # 项目配置
```

## API 接口

### 推荐接口

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "query": "推荐几部科幻片",
    "top_k": 10
  }'
```

### 健康检查

```bash
curl http://localhost:8000/health
```

## 开发计划

- [x] MVP 版本 (基础 Agent + 推荐 + 对话)
- [ ] RAG 知识库集成
- [ ] 流式响应支持
- [ ] 更多 Skills 实现
- [ ] 性能优化

## 技术栈

- **Web 框架**: FastAPI
- **Agent 框架**: LangGraph
- **LLM**: OpenAI GPT-4o-mini (可配置)
- **缓存**: Redis
- **推荐引擎**: 集成现有推荐系统
- **测试**: pytest

## 许可证

MIT

<br />


## 升级为工业级项目
1. JWT 认证：
  - 用传统推荐系统的 AUTH_SECRET_KEY 
  - 通过 AUTH_ENABLED 环境变量控制开关
  - 保护了 /api/history 和 /api/profile 端点
2. 输入校验：
  - Pydantic Field 限制： user_id 最长 64 字符，query 最长 500 字符， top_k 范围 1-20
  - XSS 过滤： field_validator 移除 HTML 标签和 script/style 内容

3. 用户访问控制：
  - 认证用户只能访问自己的对话历史
  - 认证用户只能修改自己的偏好信息

4. 速率限制：
  - 基于 Redis 滑动窗口，每分钟 20 次请求
  - 优先按 user_id 限流（认证用户），否则按 IP
  - 返回标准 429 状态码 + Retry-After 头

5. Prometheus 指标：暴露 /metrics 端点供 Prometheus 抓取
  - 收集的指标：
    - http_requests_total — QPS（按 method/endpoint/status）
    - http_request_duration_seconds — 请求延迟直方图
    - cache_hits_total / cache_misses_total — 缓存命中/未命中
    - llm_calls_total / llm_call_duration_seconds — LLM 调用统计
    - active_connections — 活跃 SSE 连接数
    - rate_limit_exceeded_total — 限流触发次数
6.  Prometheus 指标监控、Grafana 仪表盘

7. 用户反馈收集：推荐结果评分/点赞/踩 存储到redis ，用户画像积累（喜欢/不喜欢的电影， 传统系统评分自动同步到Agent 越来越个性化
8. 添加A/B 测试：根据用户画像，随机分配用户到不同的推荐策略（传统推荐系统 vs LLM 推荐系统），评估其效果

9. 在线推荐的指标评估，埋点：
  - 用户行为事件追踪：impression（展示）、click（点击）、detail_view（查看详情）、rating（评分）、like/dislike（点赞/踩）
  - 实时计算推荐质量指标：
    * CTR (点击率) = 点击次数 / 展示次数
    * 点赞率 / 踩率
    * 平均评分 & 评分参与率
    * Top-K 命中率 (用户评分≥4 的电影是否在推荐前K个)
    * 负反馈率 (评分≤2 或踩的比例)
    * 用户满意度指数 = (点赞×1 + 高分×0.8 + 中分×0.5 - 踩×1) / 总推荐数
    * 推荐多样性 & 新颖度
  - A/B 测试对比报告：LLM推荐 vs 传统推荐的完整指标对比
  - Prometheus 指标扩展：recommendation_events_total, recommendation_ctr, recommendation_hit_rate 等
  - API 接口：
    * POST /api/events - 记录用户行为事件
    * GET /api/evaluation/metrics - 获取评估指标
    * GET /api/evaluation/abtest/report - 获取 A/B 测试对比报告
  
10. ReAct模式
11. 容错和重试机制不完善
```
现状：部分服务有try-catch，但没有系统性容错
- 没有重试机制（LLM超时、网络抖动直接失败）
- 没有熔断器（外部服务挂了会继续请求）
- 没有降级策略（推荐不可用时无回退方案）
```
优化建议 ：加入 tenacity 重试 + circuitbreaker 熔断

现在（熔断+重试+降级）:
Agent → CircuitBreaker.call_llm()
         ├── 重试2次（指数退避：0.5s → 1s → 2s）
         ├── 连续5次失败 → 熔断60秒
         └── 熔断期间 → 降级到MockLLM ✅

Agent → trad_rec.get_recommendations()
         ├── CircuitBreaker保护
         ├── 3次失败熔断30秒
         └── 熔断时返回空数组 ✅

Agent → redis.update_profile()
         ├── CircuitBreaker保护
         ├── 5次失败熔断60秒
         └── 熔断时静默跳过 ✅

12. 异步处理和消息队列缺失
```
现状：部分后台任务是同步的
- 用户事件记录同步调用 HTTP
- 指标上报阻塞主流程
- 没有批量处理机制
```
优化建议 ：用 Redis Streams 或 Celery 做异步任务队列  

之前（同步阻塞）：
用户请求 → Agent 处理 → 等待写入记忆(50ms) → 等待写入对话历史(30ms) → 返回结果
         总耗时 = Agent时间 + 80ms

现在（异步队列）：
用户请求 → Agent 处理 → 入队(5ms) → 返回结果 ✅
                                        ↓ 后台 Worker 处理
                                   写入记忆 + 写入对话历史（不阻塞）
         总耗时 = Agent时间 + 5ms（快 16 倍！）

```python
# 1. 创建异步任务队列
class AsyncTaskQueue:
    """基于 Redis Streams 的异步任务队列"""
    
    async def enqueue(self, task_type: str, payload: dict):
        """把任务放入队列（不阻塞主流程）"""
        await redis.xadd("task_queue", {
            "type": task_type,
            "data": json.dumps(payload),
            "timestamp": str(time.time())
        })
    
    async def process_loop(self):
        """后台消费循环"""
        while True:
            messages = await redis.xread({"task_queue": last_id}, block=1000)
            for msg in messages:
                await self._handle_task(msg)
                await redis.xdel("task_queue", msg_id)
```
13. ✅ 全链路追踪 ：request_id 贯穿 API → Agent → Backend
如果现在用户反馈系统服务质量问题，没有request_id，就很难定位问题,有了request_id，就可以查看整个请求的完整链路，快速定位到问题所在

具体方案思路 ：利用 Python 的 contextvars （异步上下文变量），在 API 入口处生成 request_id，整个调用链自动携带。
```python
# 方案：contextvars + structlog 全局绑定

# 1. 创建全局上下文变量
import contextvars
request_id_var = contextvars.ContextVar("request_id", default=None)

# 2. structlog 全局配置自动注入
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # 自动注入 contextvars 到日志
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

# 3. API 入口处设置 request_id
async def generate_stream():
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    
    # 之后所有日志自动携带 request_id
    logger.info("开始处理")  # → {"request_id": "abc-123", "event": "开始处理"}
```

还可以顺便添加性能追踪：
```python
logger.info("LLM 调用完成", duration_ms=round((time.time() - start) * 1000, 2))

# 最终输出结构化性能数据：
# abc-123-def | 性能统计:
#   - Intent 分析: 2.1s
#   - ReAct 循环: 18.5s
#   - LLM 调用(共3次): 25.8s
#   - 传统推荐: 0.8s
#   - MemoryBank: 0.05s
#   - 总耗时: 28.5s
```
