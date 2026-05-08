"""
Prometheus 指标收集模块

收集 API QPS、延迟、缓存命中率等关键指标
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY

# HTTP 请求计数器
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

# HTTP 请求延迟直方图
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# 缓存命中率
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type"],
)

# LLM 调用计数器
llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["model", "status"],
)

# LLM 调用延迟
llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "LLM API call duration in seconds",
    ["model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0),
)

# 活跃连接数（SSE）
active_connections = Gauge(
    "active_connections",
    "Number of active SSE connections",
)

# 限流触发次数
rate_limit_exceeded_total = Counter(
    "rate_limit_exceeded_total",
    "Total rate limit exceeded events",
    ["client_type"],
)

# 用户反馈指标
feedback_submitted_total = Counter(
    "feedback_submitted_total",
    "Total feedback submitted",
    ["rating", "feedback_type"],
)

# A/B 测试指标
ab_test_assignments_total = Counter(
    "ab_test_assignments_total",
    "Total A/B test variant assignments",
    ["experiment_id", "variant"],
)

# 在线推荐质量指标
recommendation_events_total = Counter(
    "recommendation_events_total",
    "Total recommendation events",
    ["event_type", "strategy"],
)

recommendation_ctr = Gauge(
    "recommendation_ctr",
    "Click-through rate for recommendations",
    ["strategy", "time_window"],
)

recommendation_avg_rating = Gauge(
    "recommendation_avg_rating",
    "Average rating for recommendations",
    ["strategy", "time_window"],
)

recommendation_hit_rate = Gauge(
    "recommendation_hit_rate",
    "Hit rate at K for recommendations",
    ["strategy", "k", "time_window"],
)

recommendation_satisfaction_index = Gauge(
    "recommendation_satisfaction_index",
    "User satisfaction index for recommendations",
    ["strategy", "time_window"],
)


def record_http_request(method: str, endpoint: str, status: int, duration: float):
    """记录 HTTP 请求指标"""
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)


def record_cache_hit(cache_type: str = "recommend"):
    """记录缓存命中"""
    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str = "recommend"):
    """记录缓存未命中"""
    cache_misses_total.labels(cache_type=cache_type).inc()


def record_llm_call(model: str, status: str, duration: float):
    """记录 LLM 调用"""
    llm_calls_total.labels(model=model, status=status).inc()
    llm_call_duration_seconds.labels(model=model).observe(duration)


def record_ab_assignment(experiment_id: str, variant: str):
    """记录 A/B 测试分配"""
    ab_test_assignments_total.labels(experiment_id=experiment_id, variant=variant).inc()


def record_recommendation_event(event_type: str, strategy: str):
    """记录推荐事件"""
    recommendation_events_total.labels(event_type=event_type, strategy=strategy).inc()


def update_recommendation_metrics(strategy: str, time_window: str, metrics: dict):
    """更新推荐质量指标"""
    try:
        if "ctr" in metrics:
            recommendation_ctr.labels(strategy=strategy, time_window=time_window).set(metrics["ctr"])
        if "avg_rating" in metrics:
            recommendation_avg_rating.labels(strategy=strategy, time_window=time_window).set(metrics["avg_rating"])
        if "hit_rate_at_5" in metrics:
            recommendation_hit_rate.labels(strategy=strategy, k="5", time_window=time_window).set(metrics["hit_rate_at_5"])
        if "hit_rate_at_10" in metrics:
            recommendation_hit_rate.labels(strategy=strategy, k="10", time_window=time_window).set(metrics["hit_rate_at_10"])
        if "satisfaction_index" in metrics:
            recommendation_satisfaction_index.labels(strategy=strategy, time_window=time_window).set(metrics["satisfaction_index"])
    except Exception as e:
        pass


def get_metrics() -> bytes:
    """获取 Prometheus 格式的指标数据"""
    return generate_latest(REGISTRY)
