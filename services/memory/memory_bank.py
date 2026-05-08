"""
Agent 记忆内存服务

实现结构化记忆，支持：
1. 短期记忆（工作记忆）：当前对话的推荐列表、任务状态
2. 长期记忆（用户画像）：用户偏好、交互模式
3. 上下文锚点：代词解析所需的实体列表

类似人脑的记忆分层：
- 工作记忆 = 当前在想什么（这次推荐了哪些电影）
- 短期记忆 = 刚才聊了什么（上轮对话主题）
- 长期记忆 = 一直记得的事（用户喜欢科幻片）
"""

import json
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict

import redis.asyncio as aioredis
import structlog

from agent.config.agent_config import config

logger = structlog.get_logger()


@dataclass
class MemoryItem:
    """记忆项"""
    key: str
    value: Any
    category: str  # "recommendation" | "preference" | "context" | "entity"
    timestamp: float
    ttl: int = 3600  # 过期时间（秒）
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> "MemoryItem":
        return cls(**d)


class MemoryBank:
    """
    Agent 记忆内存
    
    按用户隔离，支持分类记忆和自动过期
    """
    
    def __init__(self):
        self._memory: Dict[str, Dict[str, List[MemoryItem]]] = {}
        self._redis: Optional[aioredis.Redis] = None
        self._connected = False
    
    async def initialize(self):
        """初始化 Redis 连接"""
        try:
            self._redis = aioredis.from_url(
                config.redis.url,
                decode_responses=True
            )
            await self._redis.ping()
            self._connected = True
            logger.info("记忆内存 Redis 连接成功")
        except Exception as e:
            logger.warning("记忆内存 Redis 连接失败，将使用内存模式", error=str(e))
            self._connected = False
    
    def _redis_key(self, user_id: str) -> str:
        return f"memory:{user_id}"
    
    async def _save_to_redis(self, user_id: str):
        """持久化到 Redis"""
        if not self._connected or user_id not in self._memory:
            return
        try:
            key = self._redis_key(user_id)
            data = {}
            for category, items in self._memory[user_id].items():
                data[category] = [item.to_dict() for item in items]
            await self._redis.set(key, json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning("保存记忆到 Redis 失败", user_id=user_id, error=str(e))
    
    async def _load_from_redis(self, user_id: str):
        """从 Redis 加载"""
        if not self._connected:
            return
        try:
            key = self._redis_key(user_id)
            data = await self._redis.get(key)
            if data:
                raw = json.loads(data)
                self._memory[user_id] = {}
                for category, items in raw.items():
                    self._memory[user_id][category] = [
                        MemoryItem.from_dict(item) for item in items
                    ]
                logger.info(f"从 Redis 恢复记忆: {user_id} ({len(raw)} 个分类)")
        except Exception as e:
            logger.warning("从 Redis 加载记忆失败", user_id=user_id, error=str(e))
    
    def _ensure_user(self, user_id: str):
        """确保用户记忆空间存在"""
        if user_id not in self._memory:
            self._memory[user_id] = {}
    
    def _clean_expired(self, user_id: str):
        """清理过期记忆"""
        if user_id not in self._memory:
            return
        now = time.time()
        for category in list(self._memory[user_id].keys()):
            self._memory[user_id][category] = [
                item for item in self._memory[user_id][category]
                if now - item.timestamp < item.ttl
            ]
            if not self._memory[user_id][category]:
                del self._memory[user_id][category]
    
    async def add(
        self,
        user_id: str,
        key: str,
        value: Any,
        category: str = "context",
        ttl: int = 3600
    ):
        """
        添加记忆
        
        Args:
            user_id: 用户ID
            key: 记忆键名
            value: 记忆值
            category: 记忆分类
            ttl: 过期时间（秒）
        """
        self._ensure_user(user_id)
        if category not in self._memory[user_id]:
            self._memory[user_id][category] = []
        
        # 移除同名旧记忆
        self._memory[user_id][category] = [
            item for item in self._memory[user_id][category]
            if item.key != key
        ]
        
        item = MemoryItem(
            key=key,
            value=value,
            category=category,
            timestamp=time.time(),
            ttl=ttl
        )
        self._memory[user_id][category].append(item)
        await self._save_to_redis(user_id)
        
        logger.debug(f"添加记忆: {user_id}/{category}/{key}")
    
    async def get(self, user_id: str, category: str, key: str = None) -> Any:
        """
        获取记忆
        
        Args:
            user_id: 用户ID
            category: 记忆分类
            key: 记忆键名（可选，不传则返回该分类所有记忆）
        
        Returns:
            记忆值，不存在返回 None
        """
        self._clean_expired(user_id)
        
        if user_id not in self._memory:
            return None
        
        if category not in self._memory[user_id]:
            return None
        
        items = self._memory[user_id][category]
        
        if key:
            for item in items:
                if item.key == key:
                    return item.value
            return None
        
        return {item.key: item.value for item in items}
    
    async def get_recent(self, user_id: str, category: str, limit: int = 1) -> List[Any]:
        """获取最近 N 条记忆"""
        self._clean_expired(user_id)
        
        if user_id not in self._memory:
            return []
        
        if category not in self._memory[user_id]:
            return []
        
        items = sorted(
            self._memory[user_id][category],
            key=lambda x: x.timestamp,
            reverse=True
        )
        return [item.value for item in items[:limit]]
    
    async def delete(self, user_id: str, category: str, key: str = None):
        """删除记忆"""
        if user_id not in self._memory:
            return
        
        if category not in self._memory[user_id]:
            return
        
        if key:
            self._memory[user_id][category] = [
                item for item in self._memory[user_id][category]
                if item.key != key
            ]
        else:
            if category in self._memory[user_id]:
                del self._memory[user_id][category]
        
        await self._save_to_redis(user_id)
    
    async def clear(self, user_id: str):
        """清空用户所有记忆"""
        if user_id in self._memory:
            del self._memory[user_id]
        if self._connected:
            try:
                await self._redis.delete(self._redis_key(user_id))
            except Exception as e:
                logger.warning("清空记忆失败", user_id=user_id, error=str(e))
        logger.info("清空用户记忆", user_id=user_id)
    
    async def save_recommendation(
        self,
        user_id: str,
        movies: List[Dict],
        query: str,
        ttl: int = 1800
    ):
        """
        保存推荐结果到记忆
        
        Args:
            user_id: 用户ID
            movies: 推荐的电影列表
            query: 用户的原始查询
            ttl: 过期时间（默认30分钟）
        """
        await self.add(
            user_id=user_id,
            key="last_recommendation",
            value={
                "movies": movies,
                "query": query,
                "movie_names": [m.get("title", "") for m in movies],
                "timestamp": time.time()
            },
            category="recommendation",
            ttl=ttl
        )
    
    async def save_preference(self, user_id: str, preference_key: str, preference_value: Any):
        """
        保存用户偏好到长期记忆
        
        Args:
            user_id: 用户ID
            preference_key: 偏好键名（如 "favorite_genre"）
            preference_value: 偏好值
        """
        existing = await self.get(user_id, "preference", preference_key)
        if existing:
            if isinstance(existing, list):
                if preference_value not in existing:
                    preference_value = existing + [preference_value]
            elif existing != preference_value:
                preference_value = [existing, preference_value]
        
        await self.add(
            user_id=user_id,
            key=preference_key,
            value=preference_value,
            category="preference",
            ttl=86400 * 30  # 30天
        )
    
    async def get_context_summary(self, user_id: str) -> str:
        """
        获取记忆上下文摘要（供 LLM 使用）
        
        Returns:
            格式化的记忆上下文字符串
        """
        self._clean_expired(user_id)
        parts = []
        
        # 上次推荐结果
        last_rec = await self.get_recent(user_id, "recommendation", limit=1)
        if last_rec:
            rec = last_rec[0]
            movies = rec.get("movies", [])
            query = rec.get("query", "")
            movie_names = rec.get("movie_names", [])
            
            if movies:
                parts.append(f"【上次推荐的电影】（对应用户查询: '{query}'）")
                for m in movies[:5]:
                    title = m.get("title", "未知")
                    genres = m.get("genres", "")
                    year = m.get("year", "")
                    rating = m.get("rating", "")
                    line = f"  - {title}"
                    if genres:
                        line += f" ({genres})"
                    if year:
                        line += f" {year}年"
                    if rating:
                        line += f" 评分:{rating}"
                    parts.append(line)
                
                parts.append(f"【电影名列表】（用于代词解析）")
                parts.append(f"  {', '.join(movie_names)}")
        
        # 用户偏好
        prefs = await self.get(user_id, "preference")
        if prefs:
            parts.append("【用户偏好】")
            for key, value in prefs.items():
                if isinstance(value, list):
                    parts.append(f"  {key}: {', '.join(str(v) for v in value)}")
                else:
                    parts.append(f"  {key}: {value}")
        
        return "\n".join(parts) if parts else ""


# 全局记忆实例
memory_bank = MemoryBank()
