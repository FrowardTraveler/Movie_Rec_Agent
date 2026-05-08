"""
请求限流模块

基于 Redis 的滑动窗口限流，防止 API 滥用
"""

import time
from typing import Tuple

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()


class RateLimiter:
    """
    滑动窗口限流器

    使用 Redis sorted set 实现精确的滑动窗口限流
    """

    def __init__(
        self, redis_client: aioredis.Redis, max_requests: int = 20, window_seconds: int = 60
    ):
        """
        Args:
            redis_client: Redis 客户端
            max_requests: 窗口内最大请求数
            window_seconds: 窗口大小（秒）
        """
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> Tuple[bool, dict]:
        """
        检查请求是否允许

        Args:
            key: 限流键（如 user_id 或 IP）

        Returns:
            (是否允许, 限流信息)
        """
        try:
            now = time.time()
            window_start = now - self.window_seconds

            redis_key = f"ratelimit:{key}"

            # 使用 pipeline 保证原子性
            pipe = self.redis.pipeline()

            # 移除窗口外的记录
            pipe.zremrangebyscore(redis_key, 0, window_start)

            # 获取窗口内的请求数
            pipe.zcard(redis_key)

            results = await pipe.execute()
            current_count = results[1]

            if current_count >= self.max_requests:
                # 计算剩余等待时间
                oldest = await self.redis.zrange(redis_key, 0, 0, withscores=True)
                remaining_seconds = 0
                if oldest:
                    oldest_time = oldest[0][1]
                    remaining_seconds = int(oldest_time + self.window_seconds - now)

                return False, {
                    "allowed": False,
                    "current": current_count,
                    "limit": self.max_requests,
                    "remaining": 0,
                    "retry_after": max(0, remaining_seconds),
                }

            # 允许请求，记录到窗口
            member = f"{now}:{id(object())}"  # 唯一 member
            await self.redis.zadd(redis_key, {member: now})
            await self.redis.expire(redis_key, self.window_seconds + 1)

            return True, {
                "allowed": True,
                "current": current_count + 1,
                "limit": self.max_requests,
                "remaining": self.max_requests - current_count - 1,
                "retry_after": 0,
            }

        except Exception as e:
            # 限流失败不阻断请求，降级放行
            logger.error("限流检查失败，降级放行", key=key, error=str(e))
            return True, {
                "allowed": True,
                "current": -1,
                "limit": self.max_requests,
                "remaining": -1,
                "retry_after": 0,
            }


# 全局限流器实例
_rate_limiter: RateLimiter = None


async def get_rate_limiter(redis_client: aioredis.Redis = None) -> RateLimiter:
    """获取或创建全局限流器"""
    global _rate_limiter
    if _rate_limiter is None and redis_client:
        _rate_limiter = RateLimiter(
            redis_client=redis_client,
            max_requests=20,  # 每分钟 20 次
            window_seconds=60,
        )
    return _rate_limiter
