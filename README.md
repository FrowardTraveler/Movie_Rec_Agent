# 🎬 智能电影推荐平台 - Movie Rec Agent

**双通道推荐系统 | 传统算法 + LLM Agent + RAG 增强 | 生产级高可用架构**

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/PostgreSQL-15+-336791?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>


> 一个融合**传统协同过滤推荐**与**大语言模型对话推荐**的双通道智能电影推荐系统。采用三层 6 智能体协作架构，结合多路 RAG 检索增强与生产级容错设计，既保留算法推荐的低延迟与规模化优势，又提供自然语言交互、复杂条件筛选与可解释推荐的体验。

---

## 📖 项目简介

针对传统推荐系统交互生硬、无法满足复杂个性化需求的痛点，本项目提出「双通道互补」的架构方案：

- **被动浏览场景**：由传统推荐引擎提供毫秒级个性化首页、分类与排行榜推荐
- **主动表达场景**：由 LLM Agent 通过自然语言对话完成复杂筛选、多轮修正与理由解释
- 两通道共享用户画像与行为数据，偏好与反馈双向影响，实现体验一致的推荐效果

项目同时完整落地了熔断器、分层超时、三级降级、全链路追踪等生产级能力，可直接作为中小型推荐系统的工程模板。

---

## ✨ 核心特性

### 🚦 双通道推荐体系

- **传统推荐通道**：经典 Recall → Ranking → ReRank 三段式流水线
  - 多路召回：YouTubeDNN 向量召回 + ItemCF 协同过滤 + 偏好召回
  - 精排模型：DeepFM 深度因子分解机 CTR 预估
  - 重排策略：MMR 最大边际相关性打散，保障内容多样性
- **LLM Agent 通道**：自然语言对话式推荐
  - 支持复杂约束（年代、类型、情绪、时长组合筛选）
  - 多轮对话修正，支持「换一批」「不要恐怖片」等反馈
  - 每部电影生成关联用户偏好的个性化推荐理由

### 🤖 三层 6 智能体协作架构

参考 MACRec (SIGIR 2024) 与 AgentRec 设计理念，严格控制 LLM 调用成本：

| 层级 | Agent 名称                | 核心职能                            | LLM 调用次数 |
| ---- | ------------------------- | ----------------------------------- | ------------ |
| 顶层 | Coordinator               | 规则路由、动态调度、结果融合        | 0 次         |
| 中层 | Intent & Preference       | 深度意图解析、硬约束提取、偏好建模  | 1 次         |
| 中层 | Retrieval & Filter        | 三路 RAG 检索、RRF 融合、硬规则过滤 | 0 次         |
| 中层 | Ranking & Multi-Objective | LLM 语义精排、多目标打分、MMR 打散  | 1 次         |
| 中层 | Explain & Dialogue        | 推荐理由生成、对话包装、主动追问    | 1 次         |
| 底层 | Reflector                 | 在线轻量反思、离线批量复盘优化      | 异步离线     |

### 🔍 多路 RAG 检索增强

- 三路并行检索：BM25 全文检索 + pgvector 语义向量检索 + Redis 实时热度检索
- RRF（倒数排名融合）算法统一排序，兼顾关键词匹配、语义相似度与群体热度
- 内置个性化过滤：自动排除已观看、负向偏好类型影片
- 最终输出 Top 30 候选集交付 LLM 精排

### 🛡️ 生产级高可用

- **三级降级机制**：Agent 故障 → 传统推荐引擎兜底 → 热门内容保底，服务零中断
- **全依赖熔断器**：LLM、ES、PG、Redis 全覆盖，三态状态机自动熔断与恢复
- **分层超时控制**：每个阶段独立时间预算，单环节阻塞不侵蚀全链路
- **缓存防雪崩**：随机过期偏移 + 空结果缓存，规避穿透与雪崩风险
- **安全加固**：JWT 认证、滑动窗口限流、敏感词过滤、Prompt 注入防护、Docker Secrets 密钥管理

### 📊 企业级可观测性

- Prometheus + Grafana 黄金信号监控大盘
- 标准化 SLO 定义与分级告警规则
- OpenTelemetry 全链路追踪，Metrics → Trace → Log 三信号串联
- 结构化日志，全链路 request_id 可追溯

---

## 🏗️ 系统架构
```
┌─────────────────────────────────────────────────────────────────────┐
│                        客户端层 (Vue.js 3)                           │
│  ┌───────────────┐            ┌───────────────────────┐             │
│  │ 传统推荐界面   │            │  AI 助手侧边栏 (SSE)   │             │
│  │ 首页 / 分类 / 榜单 │            │  对话式推荐 + 流式输出  │             │
│  └───────┬───────┘            └───────────┬───────────┘             │
└──────────┼────────────────────────────────┼─────────────────────────┘
│                                │
HTTP/REST                        HTTP/SSE
│                                │
┌──────────▼────────────────────────────────▼─────────────────────────┐
│                     Web API 网关层 (:8001)                           │
│  认证鉴权・速率限制・请求校验・CORS・路由分发                     │
└──────────┬────────────────────────────────┬─────────────────────────┘
│                                │
┌──────────▼──────────┐          ┌──────────▼─────────────────────┐   │
│ 传统推荐引擎 (:8000) │          │      LLM Agent 服务            │   │
│ 召回→精排→重排流水线 │          │  6 智能体协作 + 多路 RAG + LLM 推理 │   │
└──────────┬──────────┘          └──────────┬─────────────────────┘   │
└───────────────┬───────────────┘
▼
┌───────────────────────────────┐
│          共享数据层            │
│  用户画像・行为历史・电影元数据│
└───────────────────────────────┘
▼
┌──────────────┬──────────────┬────────────────┬──────────────────┐
│  PostgreSQL  │    Redis     │ Elasticsearch  │  可观测性组件     │
│  + pgvector  │ 缓存 / 画像 / 排行│  全文检索 / RAG  │ Prometheus+Jaeger │
└──────────────┴──────────────┴────────────────┴──────────────────┘
```
> 架构设计原则：两通道正常路径逻辑独立，故障路径逐级依赖降级；数据层全量共享，双向影响。

---

## 🎯 典型使用场景

### 传统推荐通道

- 打开首页自动获取「为你推荐」个性化影片
- 按科幻、喜剧、动作等类型分类浏览
- 查看实时热播榜、高分榜
- 关键词精准搜索影片

### LLM Agent 通道

- 简单需求：`推荐几部科幻片`
- 相似推荐：`推荐类似《星际穿越》的电影`
- 复杂约束：`推荐 90 年代、无暴力、治愈系的日本动画`
- 反馈修正：`刚才推荐的都看过，换小众一点的`
- 情绪匹配：`今天心情不好，推荐点轻松的`

---

## 🛠️ 技术栈选型

| 分类       | 技术选型                    | 版本   | 核心用途                         |
| ---------- | --------------------------- | ------ | -------------------------------- |
| 后端框架   | FastAPI                     | 0.104+ | API 服务，原生 async 与 SSE 支持 |
| 前端框架   | Vue.js 3 + Tailwind CSS     | -      | 双通道交互界面                   |
| 推荐算法   | TensorFlow                  | 2.15   | YouTubeDNN 召回、DeepFM 精排     |
| 大模型     | 通义千问 / OpenAI / vLLM    | -      | 多 Provider 路由，支持本地部署   |
| 关系数据库 | PostgreSQL + pgvector       | 15+    | 业务数据 + 向量索引存储          |
| 缓存中间件 | Redis                       | 7.0+   | 缓存、用户画像、热度排行、会话   |
| 搜索引擎   | Elasticsearch               | 9.2+   | 全文检索与 BM25 召回             |
| 监控告警   | Prometheus + Grafana        | -      | 指标采集、可视化大盘、告警       |
| 链路追踪   | OpenTelemetry + Jaeger      | -      | 分布式链路追踪                   |
| 部署方式   | Docker Compose / Kubernetes | -      | 本地开发与生产编排               |

---

## 🚀 快速上手

### 环境要求

- Docker & Docker Compose v2.0+
- 4GB+ 可用内存
- 8GB+ 可用磁盘空间
- （可选）GPU 用于本地 vLLM 模型部署

### 1. 克隆项目

```bash
git clone https://github.com/your-username/movie-rec-agent.git
cd movie-rec-agent
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入必要配置
# 至少配置 LLM_API_KEY、DATABASE_PASSWORD、JWT_SECRET
```

### 3. 一键启动全栈服务

```bash
docker compose up -d
```

### 4. 验证服务状态

```bash
# 检查存活探针
curl http://localhost:8001/health
# 预期返回: {"status":"alive"}

# 检查就绪探针
curl http://localhost:8001/ready
# 预期返回: {"status":"ready","checks":{"redis":"ok","es":"ok","pg":"ok","llm":"ok"}}
```

### 5. 访问地址

| 服务         | 访问地址                                                     | 说明                                       |
| ------------ | ------------------------------------------------------------ | ------------------------------------------ |
| 前端主站     | [http://localhost:3000](https://link.wtturl.cn/?target=http%3A%2F%2Flocalhost%3A3000&scene=im&aid=497858&lang=zh) | 双通道推荐主界面                           |
| API 文档     | [http://localhost:8001/docs](https://link.wtturl.cn/?target=http%3A%2F%2Flocalhost%3A8001%2Fdocs&scene=im&aid=497858&lang=zh) | Swagger 交互式接口文档                     |
| Grafana 监控 | [http://localhost:3001](https://link.wtturl.cn/?target=http%3A%2F%2Flocalhost%3A3001&scene=im&aid=497858&lang=zh) | 指标大盘与告警面板（默认账号 admin/admin） |
| Jaeger 追踪  | [http://localhost:16686](https://link.wtturl.cn/?target=http%3A%2F%2Flocalhost%3A16686&scene=im&aid=497858&lang=zh) | 全链路调用追踪 UI                          |

## 📂 项目结构

```
movie-rec-agent/
├── api/                           # Web API 服务 (:8001)
│   ├── controllers/               # 控制器层
│   │   ├── recommend.py           # 传统推荐接口
│   │   ├── agent.py               # Agent 对话接口
│   │   ├── search.py              # 搜索接口
│   │   ├── user.py                # 用户管理接口
│   │   └── event.py               # 行为事件接口
│   ├── agent/                     # LLM Agent 核心模块
│   │   ├── agents/                # 6 个职能 Agent 实现
│   │   ├── tools/                 # Agent 工具集（RAG检索、画像读取等）
│   │   ├── registry.py            # 工具注册中心
│   │   └── memory.py              # 上下文与记忆管理
│   ├── services/                  # 支撑服务
│   │   ├── event_service.py       # 事件收集服务
│   │   ├── cache_service.py       # 缓存服务
│   │   └── circuit_breaker.py     # 熔断器实现
│   └── main.py                    # 应用入口
├── engine/                        # 传统推荐引擎服务 (:8000)
│   ├── recall/                    # 召回层
│   ├── ranking/                   # 精排层
│   └── reranking/                 # 重排层
├── frontend/                      # 前端应用 (:3000)
│   ├── views/                     # 页面组件
│   └── components/                # 通用组件
├── infrastructure/                # 基础设施配置
│   ├── docker/                    # Docker Compose 编排
│   ├── monitoring/                # Prometheus/Grafana 配置
│   └── db/                        # 数据库初始化脚本
├── tests/                         # 测试用例
│   ├── unit/                      # 单元测试
│   ├── integration/               # 集成测试
│   └── e2e/                       # 端到端测试
├── .env.example                   # 环境变量模板
├── docker-compose.yml             # 全栈编排文件
├── 技术架构.md                    # 详细架构设计文档
├── README.md                      # 项目说明
└── LICENSE                        # 许可证
```

## 🧪 测试说明

项目遵循测试金字塔设计，单元测试占 70%、集成测试占 20%、E2E 测试占 10%。

运行测试

```bash
# 运行单元测试
pytest tests/unit -v

# 运行集成测试（需启动依赖服务）
pytest tests/integration -v

# 查看代码覆盖率
pytest --cov=api --cov=engine
```

### 核心覆盖范围

- 核心算法：RRF 融合、过滤逻辑、MMR 打散（≥90% 覆盖率）
- Agent 逻辑：路由规则、LLM 输出解析、降级兜底（≥85% 覆盖率）
- 基础设施：熔断器状态机、限流器、缓存策略（≥85% 覆盖率）

------

## 📈 可观测性

### 核心监控指标

- **延迟**：P50 / P95 / P99 请求耗时
- **流量**：QPS、活跃 SSE 连接数
- **错误**：5xx 错误率、各依赖熔断状态
- **饱和度**：CPU、内存、数据库连接池使用率

### 告警规则

- 🔴 严重：5xx 错误率 > 1% 持续 5 分钟、LLM 熔断器打开、核心依赖失联
- 🟡 警告：P95 延迟 > 2.5s、SSE 连接数超阈值、日 LLM 调用量超预算

### 链路追踪

通过 OpenTelemetry 采集跨服务调用链路，支持按 trace_id 串联指标、链路与日志，秒级定位性能瓶颈。

------

## 🛤️ 版本演进路线

表格

| 版本          | 核心目标                                     | 状态     |
| ------------- | -------------------------------------------- | -------- |
| v1.0 基础版   | 双通道基础功能、推荐引擎、用户画像共享       | ✅ 已完成 |
| v3.0 架构升级 | 三层 6 智能体落地、三路 RAG、混合排序        | ✅ 已完成 |
| v3.1 生产加固 | 三级降级、全依赖熔断、分层超时、可观测体系   | ✅ 已完成 |
| v3.2 效果优化 | A/B 分流实验、离线复盘闭环、动态权重自动调优 | ⏳ 规划中 |

------

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

提交前请确保代码通过单元测试与代码规范检查。

------

## 📄 相关文档

- [技术架构完整文档](./技术架构.md)：详细的架构设计、模块拆解、API 规范、可观测性方案
- [核心模块实现说明](./CORE_MODULE_IMPLEMENTATION.md)：代码结构与方法签名
- [系统架构原始方案](./SYSTEM_ARCHITECTURE.md)：重构前完整技术方案

------

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](./LICENSE) 文件。

------

<p align="center"> 如果项目对你有帮助，欢迎点个 Star ⭐ 支持一下～ </p> 
