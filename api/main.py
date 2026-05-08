"""
FastAPI 主应用

智能电影推荐 Agent API 入口
"""

import time
import json
import asyncio
import re
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, List, Dict, Any
from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 最先导入 tracing 模块，让 structlog 配置在所有其他模块的 logger 创建之前生效
# request_context.py 模块加载时会自动调用 setup_tracing()
from services.tracing.request_context import (
    generate_request_id,
    set_request_id,
    set_user_id,
    clear_context,
)

from agent.config.agent_config import config
from agent.multi_agent.coordinator import multi_agent_coordinator
from services.cache.redis_cache import redis_cache
from services.auth.jwt_auth import verify_token, AuthUser
from services.middleware.rate_limiter import RateLimiter
from services.tracing.request_context import (
    generate_request_id,
    set_request_id,
    set_user_id,
    clear_context,
)
from services.metrics import prometheus, record_http_request, record_cache_hit, record_cache_miss
from api.exceptions import register_exception_handlers, ForbiddenError, NotFoundError, ServiceUnavailableError, AppError, ErrorCode

logger = structlog.get_logger()


# ==================== 请求/响应模型 ====================

class RecommendRequest(BaseModel):
    """推荐请求"""
    user_id: str = Field(..., description="用户 ID", min_length=1, max_length=64)
    query: str = Field(..., description="用户输入/查询", min_length=1, max_length=500)
    top_k: int = Field(default=10, description="推荐数量", ge=1, le=20)
    
    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """XSS 过滤"""
        # 移除 HTML 标签
        v = re.sub(r'<[^>]*>', '', v)
        # 移除 script/style 标签内容
        v = re.sub(r'<script[^>]*>.*?</script>', '', v, flags=re.IGNORECASE | re.DOTALL)
        v = re.sub(r'<style[^>]*>.*?</style>', '', v, flags=re.IGNORECASE | re.DOTALL)
        return v.strip()


class RecommendResponse(BaseModel):
    """推荐响应"""
    success: bool = Field(..., description="是否成功")
    response: str = Field(..., description="响应文本")
    intent: str = Field(default="", description="识别的意图")
    latency_ms: float = Field(default=0.0, description="延迟 (毫秒)")
    error: Optional[str] = Field(None, description="错误信息")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    uptime: float


class MetricsResponse:
    """Prometheus 指标响应（纯文本）"""
    pass


# 全局限流器实例
_rate_limiter: RateLimiter = None


# ==================== 认证依赖 ====================

async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[AuthUser]:
    """
    从 Authorization header 获取当前用户
    
    如果认证未启用或 token 无效，返回 None（允许匿名访问）
    认证启用且 token 有效时，返回 AuthUser
    """
    if not authorization:
        return None
    
    # 提取 Bearer token
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = authorization
    
    user = verify_token(token)
    return user


# ==================== 应用生命周期 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    global _rate_limiter
    
    logger.info("应用启动中...")
    await redis_cache.connect()
    await multi_agent_coordinator.initialize()
    
    # 初始化限流器（每分钟 20 次）
    if redis_cache.redis_client:
        _rate_limiter = RateLimiter(
            redis_client=redis_cache.redis_client,
            max_requests=20,
            window_seconds=60,
        )
        logger.info("速率限制器已初始化", max_requests=20, window_seconds=60)
    
    # 初始化 A/B 测试服务
    from services.abtest.abtest_service import ab_test_service
    await ab_test_service.initialize(redis_cache.redis_client)
    logger.info("A/B 测试服务已初始化")
    
    # 初始化在线评估服务
    from services.evaluation.online_metrics import online_metrics_service
    await online_metrics_service.initialize(redis_cache.redis_client)
    logger.info("在线评估服务已初始化")
    
    # 初始化异步任务队列并注册处理器
    from services.queue.task_queue import task_queue
    from services.queue.workers import get_default_handlers
    await task_queue.initialize()
    for task_type, handler in get_default_handlers().items():
        task_queue.register_handler(task_type, handler)
    logger.info("异步任务队列已初始化")
    
    # 启动后台 Worker
    import asyncio
    worker_task = asyncio.create_task(task_queue.start_worker())
    
    logger.info("应用启动完成")
    
    yield
    
    # 关闭时清理
    logger.info("应用关闭中...")
    await task_queue.stop_worker()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await redis_cache.close()
    logger.info("应用已关闭")


# ==================== 创建应用 ====================

app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="智能电影推荐 Agent API",
    lifespan=lifespan,
)

# 注册全局异常处理器
register_exception_handlers(app)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Prometheus 指标收集中间件"""
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    endpoint = request.url.path
    
    # 忽略静态文件和根路径
    if not endpoint.startswith("/images") and endpoint != "/":
        record_http_request(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
            duration=duration,
        )
    
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """速率限制中间件"""
    global _rate_limiter
    
    # 如果没有初始化限流器，直接放行
    if _rate_limiter is None:
        return await call_next(request)
    
    # 健康检查不限制
    if request.url.path == "/api/health":
        return await call_next(request)
    
    # 获取限流 key（优先用 user_id，否则用 IP）
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        user = verify_token(token)
        limit_key = f"user:{user.user_id}" if user else f"ip:{request.client.host}"
    else:
        limit_key = f"ip:{request.client.host}"
    
    allowed, info = await _rate_limiter.is_allowed(limit_key)
    
    if not allowed:
        logger.warning("请求被限流", key=limit_key, info=info)
        from fastapi.responses import JSONResponse
        from api.exceptions import _build_error_response, ErrorCode
        rid = get_request_id()
        return JSONResponse(
            status_code=429,
            content=_build_error_response(
                code=ErrorCode.RATE_LIMITED.value,
                message="请求过于频繁，请稍后再试",
                status_code=429,
                details={
                    "retry_after": info["retry_after"],
                },
                request_id=rid,
            ),
            headers={
                "Retry-After": str(info["retry_after"]),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
            }
        )
    
    # 调用下一个中间件/路由
    response = await call_next(request)
    
    # 添加限流头信息
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    
    return response

# 静态文件服务 - 电影海报
image_dir = Path(r"d:\Code\Movie_Rec_Agent\data\movielens_data\image")
if image_dir.exists():
    app.mount("/images", StaticFiles(directory=str(image_dir)), name="images")
    logger.info("电影海报静态文件服务已启用", path=str(image_dir))
else:
    logger.warning("电影海报目录不存在，静态文件服务未启用", path=str(image_dir))

# 记录启动时间
start_time = time.time()


# ==================== 路由 ====================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="ok",
        version=config.app_version,
        uptime=time.time() - start_time,
    )


@app.get("/metrics")
async def metrics():
    """
    Prometheus 指标暴露端点
    
    供 Prometheus 抓取，包含 QPS、延迟、缓存命中率等指标
    """
    from fastapi.responses import Response
    return Response(
        content=prometheus.get_metrics(),
        media_type="text/plain; charset=utf-8"
    )


@app.post("/api/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    推荐接口（使用多Agent架构 + A/B 测试）
    
    处理用户的推荐请求，返回推荐结果
    内置 A/B 测试：自动分配用户到不同推荐策略并记录效果
    """
    from services.abtest.abtest_service import ab_test_service
    from services.evaluation.online_metrics import online_metrics_service
    import time as _time
    import uuid
    
    try:
        # 如果认证了，用真实 user_id
        effective_user_id = str(user.user_id) if user else request.user_id
        
        # A/B 测试：分配推荐策略
        variant = ab_test_service.assign_variant("recommend_strategy", effective_user_id) or "llm_only"
        
        session_id = str(uuid.uuid4())
        start_time = _time.time()
        
        if variant == "llm_only":
            # LLM 推荐策略
            result = await multi_agent_coordinator.process_request(
                user_input=request.query,
                user_id=effective_user_id
            )
        elif variant == "traditional":
            # 传统推荐策略（调用传统推荐系统 API）
            from services.integration.trad_rec_client import trad_rec_client
            trad_items = await trad_rec_client.get_recommendations(effective_user_id, request.top_k)
            
            # 转换为统一格式
            movie_ids = [item.movie_id for item in trad_items]
            result = {
                "response": f"为你推荐了 {len(trad_items)} 部电影（传统推荐）",
                "movies": [{"movie_id": item.movie_id, "title": item.title} for item in trad_items],
                "intent_analysis": {"intent_type": "recommend"},
                "latency_ms": 0,
            }
        else:
            # 兜底：LLM 推荐
            result = await multi_agent_coordinator.process_request(
                user_input=request.query,
                user_id=effective_user_id
            )
            variant = "llm_only"
        
        # 记录 A/B 测试结果
        latency_ms = (_time.time() - start_time) * 1000
        await ab_test_service.record_result(
            experiment_id="recommend_strategy",
            user_id=effective_user_id,
            variant=variant,
            result={
                "latency_ms": round(latency_ms, 2),
                "movie_count": len(result.get("movies", [])),
            },
        )
        
        # 记录 impression 事件（后台任务，不阻塞响应）
        movie_list = result.get("movies", [])
        if movie_list:
            impression_data = {
                "user_id": effective_user_id,
                "event_type": "impression",
                "movie_id": None,
                "query": request.query,
                "recommended_movies": [m.get("movie_id") for m in movie_list if m.get("movie_id")],
                "strategy": variant,
                "session_id": session_id,
                "metadata": {
                    "movie_count": len(movie_list),
                },
            }
            await online_metrics_service.record_event(impression_data)
        
        return RecommendResponse(
            success=True,
            response=result.get("response", ""),
            intent=result.get("intent_analysis", {}).get("intent_type", ""),
            latency_ms=result.get("latency_ms", latency_ms),
        )
        
    except Exception as e:
        logger.error("推荐接口错误", error=str(e))
        raise ServiceUnavailableError(message="推荐服务暂时不可用，请稍后重试")


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": config.app_name,
        "version": config.app_version,
        "message": "欢迎使用智能电影推荐 Agent！"
    }


@app.post("/api/chat/stream")
async def chat_stream(request: RecommendRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    流式对话接口 (SSE)
    
    支持实时流式输出思考过程和最终回复
    使用多Agent架构，通过 asyncio.Queue 实时推送 thinking 事件
    """
    # 如果认证了，用真实 user_id
    effective_user_id = str(user.user_id) if user else request.user_id
    
    # 全链路追踪：生成 request_id
    request_id = generate_request_id()
    set_request_id(request_id)
    set_user_id(effective_user_id)
    
    logger.info("请求开始", user_id=effective_user_id, query=request.query)
    
    async def generate_stream() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            
            queue = asyncio.Queue()
            
            def stream_callback(thinking_step):
                """实时推送 thinking 事件到队列"""
                step_data = json.dumps({
                    'type': 'thinking',
                    'content': thinking_step.content,
                    'step': {
                        'type': thinking_step.type,
                        'content': thinking_step.content,
                        'agent_name': thinking_step.agent_name,
                        'timestamp': thinking_step.timestamp
                    }
                }, ensure_ascii=False)
                queue.put_nowait(step_data)
            
            async def run_with_callback():
                return await asyncio.wait_for(
                    multi_agent_coordinator.process_request(
                        user_input=request.query,
                        user_id=effective_user_id,
                        stream_callback=stream_callback
                    ),
                    timeout=120.0
                )
            
            task = asyncio.create_task(run_with_callback())
            
            while True:
                try:
                    step_data = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield f"data: {step_data}\n\n"
                except asyncio.TimeoutError:
                    if task.done():
                        break
            
            result = await task
            
            response_text = result.get("response", "")
            
            if not response_text:
                logger.warning("多Agent 返回空响应")
                response_text = "抱歉，我没有理解你的意思，请再说一次。"
            
            chunk_size = 3
            
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                data_str = json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)
                yield f"data: {data_str}\n\n"
                await asyncio.sleep(0.01)
            
            end_data = json.dumps({
                'type': 'end',
                'task_plan': result.get('task_plan', []),
                'agent_results': result.get('agent_results', []),
                'latency_ms': result.get('latency_ms', 0.0)
            }, ensure_ascii=False)
            yield f"data: {end_data}\n\n"
            
        except Exception as e:
            logger.error("流式对话错误", error=str(e), exc_info=True)
            error_data = json.dumps({'type': 'error', 'message': f'系统错误: {str(e)}'}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"
        finally:
            logger.info("请求结束", request_id=request_id)
            clear_context()
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )


@app.get("/api/history/{user_id}")
async def get_dialogue_history(user_id: str, n: int = 10, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    获取对话历史
    
    Args:
        user_id: 用户 ID
        n: 获取最近 N 轮
    """
    from services.dialogue.dialogue_history import dialogue_history
    
    # 认证用户只能查看自己的历史
    if user and str(user.user_id) != user_id:
        raise ForbiddenError("无权访问其他用户的对话历史")
    
    history = dialogue_history.get_history(user_id, n)
    
    return {
        "success": True,
        "data": [
            {
                "user_input": turn.user_input,
                "agent_response": turn.agent_response,
                "intent": turn.intent,
                "skill_used": turn.skill_used
            }
            for turn in history
        ]
    }


@app.post("/api/profile/{user_id}")
async def update_user_profile(user_id: str, preferences: dict, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    更新用户偏好
    
    Args:
        user_id: 用户 ID
        preferences: 偏好信息
    """
    # 认证用户只能更新自己的偏好
    if user and str(user.user_id) != user_id:
        raise ForbiddenError("无权修改其他用户的偏好")
    
    from skills.profile.profile_skill import ProfileSkill
    
    profile_skill = ProfileSkill()
    result = await profile_skill.execute(
        user_id=user_id,
        action="update",
        preferences=preferences
    )
    
    return result


# ==================== 用户反馈接口 ====================

class FeedbackRequest(BaseModel):
    """反馈请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    query: str = Field(default="", max_length=500)
    recommended_movie_ids: list = Field(default=[])
    rated_movie_id: Optional[int] = None
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    feedback_type: str = Field(default="explicit", description="explicit 或 implicit")
    session_id: Optional[str] = None


@app.post("/api/feedback")
async def submit_feedback(request: FeedbackRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    提交推荐反馈
    
    用户可以对推荐结果进行评分（1-5 分）
    - 1-2 分：不喜欢/踩
    - 3 分：一般
    - 4-5 分：喜欢/赞
    """
    from services.feedback.feedback_service import feedback_service
    from services.evaluation.online_metrics import online_metrics_service
    
    effective_user_id = str(user.user_id) if user else request.user_id
    
    # 认证用户只能提交自己的反馈
    if user and str(user.user_id) != request.user_id:
        raise ForbiddenError("无权为其他用户提交反馈")
    
    success = await feedback_service.submit_feedback({
        "user_id": effective_user_id,
        "query": request.query,
        "recommended_movie_ids": request.recommended_movie_ids,
        "rated_movie_id": request.rated_movie_id,
        "rating": request.rating,
        "feedback_type": request.feedback_type,
        "session_id": request.session_id,
    })
    
    # 同时记录到在线评估服务
    if request.rating <= 2:
        event_type = "dislike"
    elif request.rating >= 4:
        event_type = "like"
    else:
        event_type = "rating"
    
    event_data = {
        "user_id": effective_user_id,
        "event_type": event_type,
        "movie_id": request.rated_movie_id,
        "query": request.query,
        "recommended_movies": request.recommended_movie_ids,
        "strategy": "llm_only",
        "rating": request.rating,
        "session_id": request.session_id,
    }
    await online_metrics_service.record_event(event_data)
    
    if not success:
        raise ServiceUnavailableError("提交反馈失败，请稍后重试")
    
    return {"success": True, "message": "反馈已提交"}


@app.get("/api/feedback/{user_id}")
async def get_feedback_history(user_id: str, limit: int = 20, user: Optional[AuthUser] = Depends(get_current_user)):
    """获取用户反馈历史"""
    from services.feedback.feedback_service import feedback_service
    
    if user and str(user.user_id) != user_id:
        raise ForbiddenError("无权访问其他用户的反馈历史")
    
    feedback_list = await feedback_service.get_user_feedback(user_id, limit)
    
    return {
        "success": True,
        "user_id": user_id,
        "count": len(feedback_list),
        "data": feedback_list,
    }


@app.get("/api/profile/{user_id}/stats")
async def get_user_profile_stats(user_id: str, user: Optional[AuthUser] = Depends(get_current_user)):
    """获取用户画像统计"""
    from services.feedback.feedback_service import feedback_service
    
    if user and str(user.user_id) != user_id:
        raise ForbiddenError("无权访问其他用户的画像")
    
    profile = await feedback_service.get_user_profile(user_id)
    
    return {
        "success": True,
        "data": profile,
    }


# ==================== A/B 测试接口 ====================

@app.get("/api/abtest/experiments")
async def list_ab_experiments():
    """获取所有 A/B 实验列表"""
    from services.abtest.abtest_service import ab_test_service
    
    return {
        "success": True,
        "data": ab_test_service.get_all_experiments(),
    }


@app.get("/api/abtest/{experiment_id}/stats")
async def get_ab_test_stats(experiment_id: str):
    """获取 A/B 实验统计结果"""
    from services.abtest.abtest_service import ab_test_service
    
    stats = await ab_test_service.get_experiment_stats(experiment_id)
    
    if stats is None:
        raise NotFoundError(f"实验 {experiment_id} 不存在")
    
    return {
        "success": True,
        "data": stats,
    }


# ==================== 用户行为事件接口 ====================

class UserEventRequest(BaseModel):
    """用户行为事件请求"""
    user_id: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., description="事件类型: impression/click/detail_view/rating/like/dislike")
    movie_id: Optional[int] = None
    query: str = Field(default="", max_length=500)
    recommended_movies: list = Field(default=[])
    strategy: str = Field(default="llm_only", description="推荐策略: llm_only/traditional")
    rating: Optional[int] = Field(None, ge=1, le=5, description="评分 (仅 rating 事件需要)")
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="额外元数据")


@app.post("/api/events")
async def record_user_event(request: UserEventRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    记录用户行为事件
    
    支持的事件类型:
    - impression: 推荐结果展示
    - click: 点击电影卡片
    - detail_view: 查看电影详情
    - rating: 评分电影
    - like: 点赞推荐
    - dislike: 踩推荐
    """
    from services.evaluation.online_metrics import online_metrics_service
    from fastapi import BackgroundTasks
    
    effective_user_id = str(user.user_id) if user else request.user_id
    
    if user and str(user.user_id) != request.user_id:
        raise ForbiddenError("无权为其他用户提交事件")
    
    event_data = {
        "user_id": effective_user_id,
        "event_type": request.event_type,
        "movie_id": request.movie_id,
        "query": request.query,
        "recommended_movies": request.recommended_movies,
        "strategy": request.strategy,
        "rating": request.rating,
        "session_id": request.session_id,
        "metadata": request.metadata or {},
    }
    
    success = await online_metrics_service.record_event(event_data)
    
    if not success:
        raise ServiceUnavailableError("记录事件失败，请稍后重试")
    
    return {"success": True, "message": f"事件 {request.event_type} 已记录"}


@app.post("/api/events/batch")
async def record_batch_user_events(
    requests: List[UserEventRequest],
    user: Optional[AuthUser] = Depends(get_current_user),
):
    """批量记录用户行为事件"""
    from services.evaluation.online_metrics import online_metrics_service
    
    effective_user_id = str(user.user_id) if user else None
    
    if user and any(str(user.user_id) != req.user_id for req in requests):
        raise ForbiddenError("无权为其他用户提交事件")
    
    success_count = 0
    for req in requests:
        user_id = effective_user_id or req.user_id
        event_data = {
            "user_id": user_id,
            "event_type": req.event_type,
            "movie_id": req.movie_id,
            "query": req.query,
            "recommended_movies": req.recommended_movies,
            "strategy": req.strategy,
            "rating": req.rating,
            "session_id": req.session_id,
            "metadata": req.metadata or {},
        }
        if await online_metrics_service.record_event(event_data):
            success_count += 1
    
    return {
        "success": True,
        "message": f"成功记录 {success_count}/{len(requests)} 个事件",
    }


# ==================== 在线评估指标接口 ====================

@app.get("/api/evaluation/metrics")
async def get_evaluation_metrics(
    strategy: str = "all",
    time_window: str = "24h",
):
    """
    获取在线推荐质量指标
    
    Args:
        strategy: 推荐策略 (llm_only/traditional/all)
        time_window: 时间窗口 (1h/24h/7d)
    
    Returns:
        推荐质量指标
    """
    from services.evaluation.online_metrics import online_metrics_service
    
    if strategy == "all":
        llm_metrics = await online_metrics_service.calculate_metrics("llm_only", time_window)
        traditional_metrics = await online_metrics_service.calculate_metrics("traditional", time_window)
        
        return {
            "success": True,
            "data": {
                "llm_only": llm_metrics,
                "traditional": traditional_metrics,
            },
        }
    else:
        metrics = await online_metrics_service.calculate_metrics(strategy, time_window)
        
        return {
            "success": True,
            "data": metrics,
        }


@app.get("/api/evaluation/abtest/report")
async def get_ab_test_report(time_window: str = "24h"):
    """
    获取 A/B 测试对比报告
    
    对比 LLM 推荐和传统推荐的效果差异
    """
    from services.evaluation.online_metrics import online_metrics_service
    
    comparison = await online_metrics_service.get_ab_comparison(time_window)
    
    return {
        "success": True,
        "data": comparison,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
