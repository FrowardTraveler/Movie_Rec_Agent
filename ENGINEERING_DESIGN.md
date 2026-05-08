# 🏗️ Movie Rec Agent — 工程设计文档

> 本文档深入解析项目中 9 个核心设计决策的 **为什么做**、**怎么做**、**优缺点**，体现工程思维。

---

## 1. 为什么采用多 Agent 协作架构？

### 💡 设计动机

LLM 应用最常见的问题是 **Single Prompt 膨胀**——把所有逻辑塞到一个 Prompt 里，导致：

- **维护困难**：一个 Prompt 几百行，改一个功能可能影响其他功能
- **调试困难**：输出不对，不知道是哪个环节出了问题
- **无法并行**：搜索和推荐必须串行等待
- **不可复用**：推荐逻辑和搜索逻辑耦合在一起

**核心问题：一个 LLM 调用要干太多事，职责不清晰。**

### 🛠️ 设计方案

```
用户请求
    ↓
MasterAgent ── 意图识别，动态路由
    ↓
┌──────────┬──────────┬──────────┐
│Recommend │  Search   │ Summary  │
│Agent     │  Agent    │ Agent    │
│(推荐)    │  (搜索)   │ (汇总)   │
└──────────┴──────────┴──────────┘
```

- **MasterAgent**：只做意图识别，决定调用哪些子 Agent
- **RecommendAgent**：只做电影推荐
- **SearchAgent**：只做精准搜索
- **SummaryAgent**：只做结果汇总和回复生成

### ✅ 优点

- **职责清晰**：每个 Agent 只做一件事，Prompt 短小精悍
- **易于调试**：输出不对可以直接定位到具体 Agent
- **易于扩展**：新增 AnalysisAgent、KnowledgeAgent 只需注册
- **支持并行**：推荐和搜索可以同时执行

### ❌ 缺点

- **多次 LLM 调用**：MasterAgent 1 次 + 子 Agent N 次，成本和延迟增加
- **上下文丢失风险**：Agent 之间通过结构化数据传递，可能丢失语义
- **复杂度增加**：需要协调器管理 Agent 生命周期和数据流

### 🤔 工程权衡

> **决策：接受多次 LLM 调用的成本，换取可维护性和可扩展性。**
>
> 原因：生产环境中，代码的可维护性比节省几次 API 调用更重要。如果后期成本成为问题，可以通过 Prompt 优化减少调用次数，而不是回到 Single Prompt 模式。

---

## 2. 为什么需要 ReAct 推理循环？

### 💡 设计动机

传统 LLM 推荐是 **一次性生成**：

```
用户: "推荐几部好电影，要评分高的"
LLM: 直接输出 4 部电影
```

问题：
- LLM 不知道推荐结果是否满足用户要求
- 如果用户要求"至少 5 部"，LLM 可能只给了 3 部
- 推荐结果质量不可控，没有自我验证机制

**核心问题：LLM 没有"思考-验证-调整"的能力。**

### 🛠️ 设计方案

实现 **Thought → Action → Observation → Reflection** 循环：

```python
for iteration in range(max_iterations):  # 最多 3 次
    # 1. Thought: 分析当前状态
    thought = analyze_state(user_query, previous_results)
    
    # 2. Action: 决定执行哪些任务
    actions = plan_actions(thought)
    
    # 3. Observation: 执行任务，收集结果
    observations = execute_parallel(actions)
    
    # 4. Reflection: 评估结果是否满意
    reflection = evaluate_results(observations)
    
    if reflection.satisfied:
        break  # 结果满意，退出循环
    else:
        task_plan = adjust_plan(reflection.reason)  # 调整计划，继续循环
```

### ✅ 优点

- **自我纠错**：结果不满意时自动调整
- **动态调整**：根据中间结果决定是否需要更多操作
- **质量可控**：Reflection 阶段可以验证推荐数量、多样性等
- **可解释**：每次循环的 Thought/Action/Observation 都可以记录

### ❌ 缺点

- **延迟增加**：每次循环都需要调用 LLM，最多 3 次循环
- **可能过度思考**：简单请求也可能走完整循环
- **成本高**：3 次循环 = 3 倍 LLM 调用

### 🤔 工程权衡

> **决策：限制最多 3 次迭代，超时自动退出。**
>
> 原因：无限循环会失控，3 次是一个经验值——足够让 Agent 自我纠正，又不会造成明显的延迟。简单请求通常 1 次就满意退出。

---

## 3. 为什么需要熔断器（Circuit Breaker）？

### 💡 设计动机

没有熔断器时：

```
LLM 服务超时 → Agent 继续请求 → 继续超时 → 继续超时...
传统推荐挂了 → Agent 继续请求 → 继续失败 → 继续失败...
```

问题：
- **级联故障**：一个服务挂了，拖垮整个系统
- **资源浪费**：持续请求已知不可用的服务
- **用户等待**：每次请求都要等到超时才返回

**核心问题：系统没有自我保护机制。**

### 🛠️ 设计方案

实现 **CLOSED → OPEN → HALF_OPEN → CLOSED** 状态机：

```
正常状态 (CLOSED)
    ↓ 连续 5 次失败
熔断状态 (OPEN) → 直接拒绝请求，不等待超时
    ↓ 60 秒后
试探状态 (HALF_OPEN) → 允许 1 次请求试探
    ↓ 成功 2 次 → 恢复正常 (CLOSED)
    ↓ 失败 → 继续熔断 (OPEN)
```

三层保护：

```
Agent → CircuitBreaker.call_llm()
         ├── 重试 2 次（指数退避：0.5s → 1s → 2s）
         ├── 连续 5 次失败 → 熔断 60 秒
         └── 熔断期间 → 降级到 MockLLM ✅

Agent → trad_rec.get_recommendations()
         ├── CircuitBreaker 保护
         ├── HTTP 超时 15 秒
         └── 熔断时返回空数组 ✅

Agent → redis.update_profile()
         ├── CircuitBreaker 保护
         └── 熔断时静默跳过 ✅
```

### ✅ 优点

- **快速失败**：熔断后直接拒绝，不等超时
- **自动恢复**：服务恢复后自动从 OPEN → HALF_OPEN → CLOSED
- **级联隔离**：一个服务挂了不影响其他服务
- **降级方案**：LLM 熔断时降级 MockLLM，保证系统可用

### ❌ 缺点

- **状态管理**：需要维护每个服务的熔断状态
- **参数调优**：失败阈值、恢复时间需要根据实际情况调整
- **可能误判**：网络抖动可能触发不必要的熔断

### 🤔 工程权衡

> **决策：LLM 熔断阈值 5 次、恢复 60 秒，传统推荐 5 次、恢复 60 秒。**
>
> 原因：5 次失败意味着不是偶然抖动，而是持续性问题。60 秒恢复时间是平衡——太短可能服务还没恢复，太长用户等待太久。如果线上数据表明参数不合适，可以动态调整。

---

## 4. 为什么需要记忆内存系统？

### 💡 设计动机

没有记忆系统时，每次对话都是 **无状态** 的：

```
用户第 1 次: "推荐几部科幻片"
AI: 推荐了《星际穿越》《盗梦空间》《银翼杀手》

用户第 2 次: "再推荐几部"
AI: 又推荐了《星际穿越》《盗梦空间》...  ← 重复推荐！
```

问题：
- **推荐重复**：不知道上次推荐了什么
- **偏好丢失**：用户说"我喜欢科幻片"，下次对话就忘了
- **上下文断裂**：多轮对话缺乏承接性

**核心问题：Agent 没有记忆，无法利用历史信息。**

### 🛠️ 设计方案

```python
class MemoryBank:
    # 短期记忆：最近 30 分钟的推荐结果
    async def save_recommendation(self, user_id, movies, query, ttl=1800):
        await self.add(user_id, "last_recommendation", {
            "movies": movies,
            "query": query,
            "timestamp": time.time()
        }, category="recommendation", ttl=1800)
    
    # 长期记忆：用户偏好（自动累积）
    async def save_preference(self, user_id, key, value):
        existing = await self.get(user_id, "preference", key)
        if isinstance(existing, list):
            existing.append(value)  # 累积为列表
        else:
            await self.add(user_id, key, [value], category="preference")
    
    # 推荐去重：从记忆中提取已推荐电影
    async def get_recommended_movies(self, user_id) -> List[str]:
        rec = await self.get(user_id, "recommendation", "last_recommendation")
        return [m["title"] for m in rec["movie_names"]]
```

### ✅ 优点

- **推荐去重**：自动跳过已推荐的电影
- **偏好累积**：用户多次提到的偏好自动记录
- **TTL 自动过期**：短期记忆自动清理，避免内存泄漏
- **多用户隔离**：每个用户的记忆独立存储

### ❌ 缺点

- **内存占用**：大量用户的记忆需要 Redis 存储
- **一致性**：Redis 和 Agent 内存之间可能不一致
- **TTL 设置**：30 分钟是否合适需要线上验证

### 🤔 工程权衡

> **决策：短期记忆用内存 + 30 分钟 TTL，长期记忆持久化到 Redis。**
>
> 原因：短期记忆访问频繁，放内存快；长期记忆需要持久化，防止 Agent 重启丢失。30 分钟 TTL 覆盖大多数多轮对话场景，用户中断对话超过 30 分钟后重新开始，记忆过期也合理。

---

## 5. 为什么需要异步任务队列？

### 💡 设计动机

没有异步队列时，后台任务是 **同步阻塞** 的：

```
用户请求 → Agent 处理 → 等待写入记忆(50ms) 
                      → 等待写入对话历史(30ms) 
                      → 返回结果
         总耗时 = Agent时间 + 80ms
```

问题：
- **响应慢**：后台写入阻塞主流程
- **不重试**：写入失败直接丢弃
- **无隔离**：后台任务失败影响主流程

**核心问题：后台任务不应该阻塞用户请求。**

### 🛠️ 设计方案

```python
# 主流程：入队即返回
await task_queue.enqueue("save_recommendation", {
    "user_id": user_id,
    "movies": movies,
    "query": query
})
await task_queue.enqueue("save_dialogue", {
    "user_id": user_id,
    "turn": dialogue_turn
})
# 直接返回，不等后台任务完成

# 后台 Worker：异步消费
async def process_loop():
    while True:
        messages = await redis.xread({"task_queue": last_id}, block=1000)
        for msg in messages:
            await self._handle_task(msg)
            await redis.xdel("task_queue", msg_id)
```

### ✅ 优点

- **延迟降低 16 倍**：80ms → 5ms
- **失败重试**：Worker 可以重试失败的后台任务
- **主流程隔离**：后台任务失败不影响用户请求
- **批量处理**：可以攒一批任务一起处理

### ❌ 缺点

- **最终一致性**：记忆写入可能延迟，用户立即查看可能看不到
- **复杂度增加**：需要维护 Worker 进程
- **消息丢失风险**：Redis 宕机可能丢失未处理的消息

### 🤔 工程权衡

> **决策：接受最终一致性，优先保证响应速度。**
>
> 原因：用户推荐请求的响应速度比记忆写入的及时性重要得多。记忆写入延迟几秒对用户无感知。如果担心消息丢失，可以用 Redis AOF + RDB 持久化。

---

## 6. 为什么需要全链路追踪（request_id）？

### 💡 设计动机

没有 request_id 时：

```
2026-05-04 14:12:14 [info] 请求开始
2026-05-04 14:12:24 [info] LLM 意图分析
2026-05-04 14:12:34 [info] 推荐成功
2026-05-04 14:12:34 [info] 请求开始        ← 这是谁的请求？
2026-05-04 14:12:44 [error] LLM 调用失败    ← 是哪个请求失败了？
```

问题：
- **日志混乱**：并发请求的日志混在一起
- **无法定位**：用户反馈问题，不知道是哪次请求
- **性能分析**：不知道请求在哪个环节慢

**核心问题：没有请求标识，无法追踪请求生命周期。**

### 🛠️ 设计方案

```python
# 1. 创建全局上下文变量（异步安全）
import contextvars
request_id_var = contextvars.ContextVar("request_id", default=None)

# 2. structlog 全局配置，自动注入 contextvars
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,  # 自动注入
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

# 3. API 入口处设置
request_id = generate_request_id()  # req-abc123def456
set_request_id(request_id)
set_user_id(effective_user_id)

# 之后所有日志自动携带 request_id
logger.info("请求开始")  # → {"request_id": "req-abc123", ...}
logger.info("LLM 调用")   # → {"request_id": "req-abc123", ...}
```

### ✅ 优点

- **全链路追踪**：一个 request_id 贯穿整个请求生命周期
- **快速定位**：用户反馈问题，grep request_id 即可找到所有日志
- **性能分析**：记录每个环节的耗时，分析瓶颈
- **无侵入**：contextvars 自动传递，不需要在每个方法里传递参数

### ❌ 缺点

- **异步边界问题**：跨线程/跨进程时 contextvars 可能丢失
- **存储开销**：每条日志多存一个 request_id
- **请求 ID 冲突**：UUID 生成理论上有冲突可能（极低）

### 🤔 工程权衡

> **决策：使用 contextvars + structlog 自动注入，而非手动传递。**
>
> 原因：手动传递 request_id 需要在每个方法签名里加参数，侵入性强。contextvars 在同一个 async task 内自动传递，不需要修改现有代码。对于跨进程的场景（如 Agent → 后端），通过 HTTP Header 传递 request_id。

---

## 7. 为什么需要 A/B 测试？

### 💡 设计动机

没有 A/B 测试时，无法回答：

- LLM 推荐真的比传统推荐好吗？
- 用户更喜欢哪种推荐方式？
- 新的推荐策略是否提升了效果？

**核心问题：没有数据对比，优化靠感觉。**

### 🛠️ 设计方案

```python
# A/B 测试分配：50% LLM, 50% 传统
variant = abtest_service.assign_variant(user_id)

if variant == "llm_only":
    # 多 Agent 协作推荐
    result = await multi_agent_coordinator.process(...)
elif variant == "traditional":
    # 传统推荐流水线
    result = await trad_rec_client.get_recommendations(...)

# 记录用户行为，后续分析
await online_metrics.record_event({
    "user_id": user_id,
    "strategy": variant,  # 记录用户分到了哪个组
    "event_type": "click",
    "movie_id": movie_id,
})
```

### ✅ 优点

- **数据驱动**：用实际数据对比不同策略效果
- **科学决策**：不是凭感觉，而是看 CTR、满意度等指标
- **灰度发布**：新功能可以先给 10% 用户试用

### ❌ 缺点

- **实现复杂**：需要分配、记录、分析完整流程
- **需要样本量**：样本太少统计不显著
- **当前是 mock**：traditional 分支还没有接入真正的推荐流水线

### 🤔 工程权衡

> **决策：先搭框架，再逐步完善。**
>
> 原因：A/B 测试的框架搭建成本不高，但收益很大。即使当前 traditional 分支是 mock，框架搭好了后续接入真实推荐流水线只需改实现，不需要改框架。

---

## 8. 为什么需要全局异常处理？

### 💡 设计动机

没有全局异常处理时：

```python
# 端点 A
raise HTTPException(status_code=403, detail="无权访问")

# 端点 B
return {"success": False, "error": "xxx"}

# 端点 C
raise ValueError("内部错误")  # → 500 裸异常
```

问题：
- **格式不统一**：前端需要处理多种错误格式
- **错误信息泄露**：裸异常可能暴露内部实现
- **难以监控**：不知道哪些错误频繁发生

**核心问题：错误响应格式混乱，用户体验差。**

### 🛠️ 设计方案

```python
# 1. 定义统一错误码
class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"

# 2. 自定义异常类
class ForbiddenError(AppError):
    def __init__(self, message="无权执行此操作", details=None):
        super().__init__(ErrorCode.FORBIDDEN, message, 403, details)

# 3. 全局异常处理器
@app.exception_handler(AppError)
async def app_error_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={
        "success": False,
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": get_request_id(),
        }
    })

# 4. 端点中使用
raise ForbiddenError("无权访问其他用户的对话历史")
```

### ✅ 优点

- **格式统一**：所有错误返回相同格式，前端处理简单
- **安全**：内部错误统一返回"系统内部错误"，不暴露细节
- **可追踪**：每个错误都携带 request_id，方便定位
- **易于监控**：按错误码统计，知道哪些错误频繁发生

### ❌ 缺点

- **开发习惯**：团队需要统一使用自定义异常
- **错误码管理**：新增错误类型需要维护 ErrorCode 枚举

### 🤔 工程权衡

> **决策：保留 HTTPException 处理器作为兜底，同时支持自定义异常。**
>
> 原因：不是所有代码都能立即迁移到自定义异常。保留 HTTPException 处理器可以兼容现有代码，逐步迁移。

---

## 9. 为什么选择微服务架构（Agent :8001 + 后端 :8000）？

### 💡 设计动机

为什么不把所有东西塞在一个服务里？

```
单服务方案:
┌─────────────────────────────────┐
│  FastAPI                        │
│  ├── LLM Agent                  │
│  ├── DeepFM 推荐模型            │
│  ├── YouTubeDNN 推荐模型        │
│  ├── 用户认证                   │
│  └── 数据库操作                 │
└─────────────────────────────────┘

问题:
- 模型更新需要重启整个服务（Agent 也受影响）
- 推荐模型和 Agent 的依赖不同，容易冲突
- 无法独立扩缩容（Agent 需要 GPU，推荐需要 CPU）
```

**核心问题：单一服务无法独立扩展和维护。**

### 🛠️ 设计方案

```
微服务方案:
┌──────────────────┐    ┌──────────────────┐
│  Agent (:8001)    │───▶│  后端 (:8000)    │
│  ├── LangGraph    │    │  ├── DeepFM      │
│  ├── LLM 调用     │    │  ├── YouTubeDNN  │
│  ├── 多 Agent     │    │  ├── ItemCF      │
│  └── API 接口     │    │  └── 推荐流水线  │
└──────────────────┘    └──────────────────┘
       独立部署               独立部署
       独立扩展               独立扩展
```

通过 HTTP 调用后端推荐 API，两个服务：
- **独立部署**：更新推荐模型不需要重启 Agent
- **独立扩展**：Agent 可以部署多个实例应对高并发
- **依赖隔离**：两个服务的 Python 依赖不会冲突
- **技术栈灵活**：后端可以用 PyTorch，Agent 可以用 LangChain

### ✅ 优点

- **独立部署**：更新一个服务不影响另一个
- **独立扩展**：按需扩缩容
- **技术解耦**：不同服务可以用不同技术栈
- **故障隔离**：一个服务挂了，另一个可以继续工作

### ❌ 缺点

- **网络开销**：HTTP 调用增加 ~50ms 延迟
- **部署复杂**：需要管理多个服务
- **分布式问题**：需要处理网络超时、重试、熔断

### 🤔 工程权衡

> **决策：接受微服务的复杂度，换取可维护性和可扩展性。**
>
> 原因：对于面试项目，微服务架构展示了你对生产环境的理解。虽然增加了部署复杂度，但 Docker Compose 可以一键启动所有服务，降低了运维负担。如果后期需要优化性能，可以通过 gRPC 替代 HTTP 减少延迟。

---

## 📊 总结：工程思维体现

| 设计决策 | 核心问题 | 解决方案 | 权衡 |
|---------|---------|---------|------|
| 多 Agent 协作 | Single Prompt 膨胀 | 职责分离，动态路由 | 成本 vs 可维护性 |
| ReAct 循环 | LLM 无自我验证 | Thought-Action-Observation-Reflection | 延迟 vs 质量 |
| 熔断器 | 级联故障 | CLOSED→OPEN→HALF_OPEN 状态机 | 误判 vs 保护 |
| 记忆内存 | 无状态重复推荐 | 短期+长期记忆，TTL 过期 | 内存 vs 体验 |
| 异步队列 | 后台任务阻塞 | Redis Streams + Worker | 一致性 vs 速度 |
| 全链路追踪 | 日志无法关联 | contextvars + request_id | 存储 vs 可观测 |
| A/B 测试 | 优化靠感觉 | 数据驱动对比 | 样本量 vs 决策 |
| 全局异常 | 错误格式混乱 | 统一错误码 + 处理器 | 迁移成本 vs 体验 |
| 微服务 | 单服务无法扩展 | Agent + 后端分离 | 网络开销 vs 灵活 |

**工程思维的核心：没有完美的方案，只有基于场景的权衡。**

每个设计决策都有优点和缺点，关键是：
1. **明确问题**：为什么需要这个设计？
2. **分析选项**：有哪些方案？各自的优缺点是什么？
3. **做出权衡**：基于当前场景选择最合适的方案
4. **留有后路**：设计可以后续调整，不要过度设计
