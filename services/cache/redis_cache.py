"""
Redis 缓存服务

提供推荐结果的缓存功能，降低延迟
"""

import hashlib
import json
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog

from agent.config.agent_config import config

logger = structlog.get_logger()


class RedisCache:
    """
    Redis 缓存服务

    用于缓存推荐结果，降低响应延迟
    """

    def __init__(self):
        """初始化 Redis 缓存"""
        self.redis_config = config.redis
        self.redis_client = None
        self._connected = False

    async def connect(self):
        """
        连接 Redis 服务器

        如果连接失败，不会抛出异常，而是降级为无缓存模式
        """
        try:
            self.redis_client = aioredis.from_url(self.redis_config.url, decode_responses=True)

            # 测试连接
            await self.redis_client.ping()
            self._connected = True
            logger.info("Redis 连接成功", url=self.redis_config.url)

        except Exception as e:
            logger.warning("Redis 连接失败，将使用无缓存模式", error=str(e))
            self._connected = False

    async def get(self, key: str) -> Optional[Any]:
        """
        从缓存获取数据

        Args:
            key: 缓存键

        Returns:
            缓存数据，如果不存在或连接失败则返回 None
        """
        if not self._connected:
            return None

        try:
            data = await self.redis_client.get(key)
            if data:
                logger.debug("缓存命中", key=key)
                return json.loads(data)
            else:
                logger.debug("缓存未命中", key=key)
                return None
        except Exception as e:
            logger.warning("缓存获取失败", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存数据

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间 (秒)，默认使用配置的 cache_ttl

        Returns:
            是否设置成功
        """
        if not self._connected:
            return False

        if ttl is None:
            ttl = self.redis_config.cache_ttl

        try:
            await self.redis_client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
            logger.debug("缓存设置成功", key=key, ttl=ttl)
            return True
        except Exception as e:
            logger.warning("缓存设置失败", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        删除缓存数据

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        if not self._connected:
            return False

        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.warning("缓存删除失败", key=key, error=str(e))
            return False

    def build_cache_key(self, prefix: str, **kwargs) -> str:
        """
        构建缓存键

        Args:
            prefix: 缓存键前缀
            **kwargs: 参数，用于生成唯一的缓存键

        Returns:
            缓存键字符串
        """
        # 将参数排序并编码为字符串
        param_str = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        # 使用 MD5 生成哈希值，缩短键长度
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]

        return f"{prefix}:{param_hash}"

    async def close(self):
        """关闭 Redis 连接"""
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False
            logger.info("Redis 连接已关闭")


# 全局 Redis 缓存实例
redis_cache = RedisCache()
