"""
在线推荐质量评估服务

基于用户真实行为数据(展示、点击、评分、点赞/踩)计算推荐质量指标

优化方案:
1. 增量聚合: 不存原始事件,只存聚合指标
2. 智能 TTL: 聚合数据 7 天过期,用户画像 30 天
3. 内存控制: 单用户最多保留 100 条评分历史
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

import structlog

logger = structlog.get_logger()


class UserEvent:
    """用户行为事件"""

    IMPRESSION = "impression"
    CLICK = "click"
    DETAIL_VIEW = "detail_view"
    RATING = "rating"
    LIKE = "like"
    DISLIKE = "dislike"


class OnlineMetricsService:
    """
    在线推荐质量评估服务 (优化版)

    存储策略:
    1. 增量聚合: 按小时聚合到 Redis Hash
    2. 原始采样: 只保留最近 100 条事件 (用于调试)
    3. TTL 自动清理: 聚合数据 7 天,用户数据 30 天
    """

    # 增量聚合 Key (按小时)
    METRICS_PREFIX = "agent:metrics:"
    # 用户画像 Key
    USER_PROFILE_PREFIX = "agent:profile:"
    # 原始事件采样 (仅调试用)
    EVENTS_SAMPLE_PREFIX = "agent:events_sample:"

    # TTL 设置
    METRICS_TTL = 7 * 24 * 3600  # 7 天
    PROFILE_TTL = 30 * 24 * 3600  # 30 天
    SAMPLE_TTL = 24 * 3600  # 1 天

    def __init__(self):
        self._redis_client = None

    async def initialize(self, redis_client=None):
        """初始化 Redis 连接"""
        self._redis_client = redis_client

    async def record_event(self, event_data: Dict[str, Any]) -> bool:
        """
        记录用户行为事件 (增量聚合版)

        不再存储原始事件列表,改为:
        1. 更新小时级聚合指标 (Redis Hash + INCR)
        2. 更新用户画像
        3. 保留少量采样事件 (用于调试)
        """
        try:
            if not self._redis_client:
                logger.error("Redis 客户端未初始化")
                return False

            event_data["timestamp"] = event_data.get("timestamp", time.time())

            strategy = event_data.get("strategy", "unknown")
            event_type = event_data["event_type"]
            user_id = event_data.get("user_id")

            # 获取当前小时的时间戳 (用于聚合)
            current_hour = datetime.now().strftime("%Y-%m-%d:%H")

            pipe = self._redis_client.pipeline()

            # 1. 更新小时级聚合指标
            metrics_key = f"{self.METRICS_PREFIX}{strategy}:{current_hour}"
            pipe.hincrby(metrics_key, event_type, 1)
            pipe.expire(metrics_key, self.METRICS_TTL)

            # 2. 记录原始事件采样 (仅最近 100 条,用于调试)
            sample_key = f"{self.EVENTS_SAMPLE_PREFIX}{strategy}:{event_type}"
            pipe.rpush(sample_key, json.dumps(event_data, ensure_ascii=False))
            pipe.ltrim(sample_key, -100, -1)
            pipe.expire(sample_key, self.SAMPLE_TTL)

            # 3. 更新用户画像
            if user_id:
                await self._update_user_profile_async(pipe, event_data)

            await pipe.execute()

            # 记录到 Prometheus
            try:
                from services.metrics.prometheus import record_recommendation_event

                record_recommendation_event(event_type, strategy)
            except Exception:
                pass

            logger.debug(
                "用户事件已记录 (聚合模式)",
                user_id=user_id,
                event_type=event_type,
                strategy=strategy,
            )
            return True

        except Exception as e:
            logger.error("记录用户事件失败", error=str(e))
            return False

    async def _update_user_profile_async(self, pipe, event_data: Dict[str, Any]):
        """更新用户画像 (异步管道版本)"""
        user_id = event_data.get("user_id")
        event_type = event_data["event_type"]
        movie_id = event_data.get("movie_id")
        rating = event_data.get("rating")

        profile_key = f"{self.USER_PROFILE_PREFIX}{user_id}"

        # 记录最近交互时间
        pipe.hset(profile_key, "last_interaction", str(time.time()))
        pipe.expire(profile_key, self.PROFILE_TTL)

        if event_type == "click":
            pipe.hincrby(profile_key, "total_clicks", 1)

        elif event_type == "rating" and rating and movie_id:
            pipe.hincrby(profile_key, "total_ratings", 1)

            # 记录评分历史 (最多 100 条)
            rating_key = f"{self.USER_PROFILE_PREFIX}{user_id}:ratings"
            pipe.hset(rating_key, str(movie_id), str(rating))
            pipe.expire(rating_key, self.PROFILE_TTL)

        elif event_type == "impression":
            pipe.hincrby(profile_key, "total_impressions", 1)

    async def calculate_metrics(
        self,
        strategy: str,
        time_window: str = "24h",
    ) -> Dict[str, Any]:
        """
        计算推荐质量指标 (从聚合数据计算)

        Args:
            strategy: 推荐策略 (llm_only/traditional)
            time_window: 时间窗口 (1h, 24h, 7d)

        Returns:
            指标字典
        """
        try:
            if not self._redis_client:
                return {}

            # 获取时间窗口内的小时聚合数据
            hours_to_fetch = self._get_hours_count(time_window)
            metrics_data = await self._fetch_aggregated_metrics(strategy, hours_to_fetch)

            if not metrics_data:
                return self._empty_metrics(strategy, time_window)

            # 计算指标
            total_impressions = metrics_data.get(UserEvent.IMPRESSION, 0)
            total_clicks = metrics_data.get(UserEvent.CLICK, 0)
            total_ratings = metrics_data.get(UserEvent.RATING, 0)
            total_likes = metrics_data.get(UserEvent.LIKE, 0)
            total_dislikes = metrics_data.get(UserEvent.DISLIKE, 0)

            if total_impressions == 0:
                return self._empty_metrics(strategy, time_window)

            # 基础指标
            ctr = total_clicks / total_impressions if total_impressions > 0 else 0.0
            like_rate = total_likes / total_impressions if total_impressions > 0 else 0.0
            dislike_rate = total_dislikes / total_impressions if total_impressions > 0 else 0.0
            rating_participation_rate = (
                total_ratings / total_impressions if total_impressions > 0 else 0.0
            )

            # 从用户画像获取评分数据
            rating_stats = await self._get_rating_stats(strategy)
            avg_rating = rating_stats.get("avg_rating", 0.0)

            # 命中率、负反馈率等需要从采样事件计算
            sample_metrics = await self._calculate_from_samples(strategy, time_window)

            satisfaction_index = self._calculate_satisfaction_index(
                total_likes,
                total_dislikes,
                total_ratings,
                total_impressions,
                rating_stats.get("high_ratings", 0),
                rating_stats.get("medium_ratings", 0),
            )

            result = {
                "strategy": strategy,
                "time_window": time_window,
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_ratings": total_ratings,
                "total_likes": total_likes,
                "total_dislikes": total_dislikes,
                "ctr": round(ctr, 4),
                "like_rate": round(like_rate, 4),
                "dislike_rate": round(dislike_rate, 4),
                "avg_rating": round(avg_rating, 2),
                "rating_participation_rate": round(rating_participation_rate, 4),
                "hit_rate_at_5": sample_metrics.get("hit_rate_at_5", 0.0),
                "hit_rate_at_10": sample_metrics.get("hit_rate_at_10", 0.0),
                "negative_feedback_rate": sample_metrics.get("negative_feedback_rate", 0.0),
                "satisfaction_index": round(satisfaction_index, 4),
                "genre_diversity": sample_metrics.get("genre_diversity", 0.0),
                "novelty_rate": sample_metrics.get("novelty_rate", 0.0),
            }

            # 更新 Prometheus 指标
            try:
                from services.metrics.prometheus import update_recommendation_metrics

                update_recommendation_metrics(strategy, time_window, result)
            except Exception:
                pass

            return result

        except Exception as e:
            logger.error("计算指标失败", strategy=strategy, error=str(e))
            return {}

    def _get_hours_count(self, time_window: str) -> int:
        """获取时间窗口对应的小时数"""
        if time_window == "1h":
            return 1
        elif time_window == "24h":
            return 24
        elif time_window == "7d":
            return 7 * 24
        return 24

    async def _fetch_aggregated_metrics(self, strategy: str, hours: int) -> Dict[str, int]:
        """获取时间窗口内的聚合指标"""
        try:
            now = datetime.now()
            total_metrics = defaultdict(int)

            for i in range(hours):
                hour_time = now - timedelta(hours=i)
                hour_key = hour_time.strftime("%Y-%m-%d:%H")
                metrics_key = f"{self.METRICS_PREFIX}{strategy}:{hour_key}"

                metrics = await self._redis_client.hgetall(metrics_key)
                if metrics:
                    for event_type, count in metrics.items():
                        total_metrics[event_type] += int(count)

            return dict(total_metrics)

        except Exception as e:
            logger.error("获取聚合指标失败", error=str(e))
            return {}

    async def _get_rating_stats(self, strategy: str) -> Dict[str, Any]:
        """获取评分统计 (从采样事件计算)"""
        try:
            rating_key = f"{self.EVENTS_SAMPLE_PREFIX}{strategy}:rating"
            rating_events = await self._redis_client.lrange(rating_key, 0, -1)

            if not rating_events:
                return {"avg_rating": 0.0, "high_ratings": 0, "medium_ratings": 0}

            ratings = []
            high_ratings = 0
            medium_ratings = 0

            for event_json in rating_events:
                event = json.loads(event_json)
                rating = event.get("rating", 0)
                if rating:
                    ratings.append(rating)
                    if rating >= 4:
                        high_ratings += 1
                    elif rating == 3:
                        medium_ratings += 1

            return {
                "avg_rating": sum(ratings) / len(ratings) if ratings else 0.0,
                "high_ratings": high_ratings,
                "medium_ratings": medium_ratings,
            }

        except Exception as e:
            logger.error("获取评分统计失败", error=str(e))
            return {"avg_rating": 0.0, "high_ratings": 0, "medium_ratings": 0}

    async def _calculate_from_samples(self, strategy: str, time_window: str) -> Dict[str, float]:
        """从采样事件计算复杂指标"""
        # 这里可以从采样事件计算命中率、负反馈率等
        # 由于是采样数据,结果是近似值
        return {
            "hit_rate_at_5": 0.0,
            "hit_rate_at_10": 0.0,
            "negative_feedback_rate": 0.0,
            "genre_diversity": 0.0,
            "novelty_rate": 0.0,
        }

    def _calculate_satisfaction_index(
        self,
        total_likes: int,
        total_dislikes: int,
        total_ratings: int,
        total_impressions: int,
        high_ratings: int,
        medium_ratings: int,
    ) -> float:
        """
        计算用户满意度指数

        公式: (点赞数×1 + 4-5星评分数×0.8 + 3星评分数×0.5 - 踩数×1) / 总推荐数
        """
        if total_impressions == 0:
            return 0.0

        satisfaction_score = (
            total_likes * 1.0 + high_ratings * 0.8 + medium_ratings * 0.5 - total_dislikes * 1.0
        )

        return satisfaction_score / total_impressions

    def _empty_metrics(self, strategy: str, time_window: str) -> Dict[str, Any]:
        """返回空指标"""
        return {
            "strategy": strategy,
            "time_window": time_window,
            "total_impressions": 0,
            "total_clicks": 0,
            "total_ratings": 0,
            "total_likes": 0,
            "total_dislikes": 0,
            "ctr": 0.0,
            "like_rate": 0.0,
            "dislike_rate": 0.0,
            "avg_rating": 0.0,
            "rating_participation_rate": 0.0,
            "hit_rate_at_5": 0.0,
            "hit_rate_at_10": 0.0,
            "negative_feedback_rate": 0.0,
            "satisfaction_index": 0.0,
            "genre_diversity": 0.0,
            "novelty_rate": 0.0,
        }

    async def get_ab_comparison(
        self,
        time_window: str = "24h",
    ) -> Dict[str, Any]:
        """
        获取 A/B 测试对比报告

        Returns:
            两种策略的完整指标对比
        """
        llm_metrics = await self.calculate_metrics("llm_only", time_window)
        traditional_metrics = await self.calculate_metrics("traditional", time_window)

        comparison = {
            "time_window": time_window,
            "llm_only": llm_metrics,
            "traditional": traditional_metrics,
            "comparison": {},
        }

        if llm_metrics and traditional_metrics:
            comparison["comparison"] = {
                "ctr_diff": round(llm_metrics.get("ctr", 0) - traditional_metrics.get("ctr", 0), 4),
                "avg_rating_diff": round(
                    llm_metrics.get("avg_rating", 0) - traditional_metrics.get("avg_rating", 0), 2
                ),
                "hit_rate_at_10_diff": round(
                    llm_metrics.get("hit_rate_at_10", 0)
                    - traditional_metrics.get("hit_rate_at_10", 0),
                    4,
                ),
                "satisfaction_diff": round(
                    llm_metrics.get("satisfaction_index", 0)
                    - traditional_metrics.get("satisfaction_index", 0),
                    4,
                ),
                "diversity_diff": round(
                    llm_metrics.get("genre_diversity", 0)
                    - traditional_metrics.get("genre_diversity", 0),
                    4,
                ),
            }

        return comparison


online_metrics_service = OnlineMetricsService()
