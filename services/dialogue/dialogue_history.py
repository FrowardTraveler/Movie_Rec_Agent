"""
对话历史管理

支持多轮对话记忆，维护用户对话上下文
支持 Redis 持久化，服务重启后不丢失
"""

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
import structlog

from agent.config.agent_config import config

logger = structlog.get_logger()


@dataclass
class DialogueTurn:
    """对话轮次"""

    user_input: str
    agent_response: str
    intent: str
    skill_used: str
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DialogueTurn":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


class DialogueHistory:
    """
    对话历史管理器

    使用滑动窗口维护最近 N 轮对话
    数据同时保存在 Redis 中，服务重启后可恢复
    """

    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        # 内存缓存（热数据）
        self.history: Dict[str, deque] = {}

        # Redis 连接
        self._redis: Optional[aioredis.Redis] = None
        self._connected = False

    async def initialize(self):
        """初始化 Redis 连接"""
        try:
            self._redis = aioredis.from_url(config.redis.url, decode_responses=True)
            await self._redis.ping()
            self._connected = True
            logger.info("对话历史 Redis 连接成功")
        except Exception as e:
            logger.warning("对话历史 Redis 连接失败，将使用内存模式", error=str(e))
            self._connected = False

    def _redis_key(self, user_id: str) -> str:
        return f"dialogue:{user_id}:turns"

    async def add_turn(
        self,
        user_id: str,
        user_input: str,
        agent_response: str,
        intent: str,
        skill_used: str,
        context: Dict[str, Any] = None,
    ):
        turn = DialogueTurn(
            user_input=user_input,
            agent_response=agent_response,
            intent=intent,
            skill_used=skill_used,
            context=context or {},
        )

        # 内存缓存
        if user_id not in self.history:
            # 先从 Redis 加载历史
            await self._load_from_redis(user_id)
            if user_id not in self.history:
                self.history[user_id] = deque(maxlen=self.max_turns)

        self.history[user_id].append(turn)

        # 持久化到 Redis
        if self._connected:
            try:
                key = self._redis_key(user_id)
                turns_json = json.dumps(
                    [t.to_dict() for t in self.history[user_id]], ensure_ascii=False
                )
                await self._redis.set(key, turns_json)
            except Exception as e:
                logger.warning("保存对话历史到 Redis 失败", user_id=user_id, error=str(e))

        logger.debug("添加对话轮次", user_id=user_id, turn_count=len(self.history[user_id]))

    async def _load_from_redis(self, user_id: str):
        """从 Redis 加载历史到内存"""
        if not self._connected:
            return

        try:
            key = self._redis_key(user_id)
            data = await self._redis.get(key)
            if data:
                turns = [DialogueTurn.from_dict(d) for d in json.loads(data)]
                self.history[user_id] = deque(turns, maxlen=self.max_turns)
                logger.info(f"从 Redis 恢复对话历史: {user_id} ({len(turns)} 轮)")
        except Exception as e:
            logger.warning("从 Redis 加载对话历史失败", user_id=user_id, error=str(e))

    def get_history(self, user_id: str, n: int = None) -> List[DialogueTurn]:
        if user_id not in self.history:
            return []
        history = list(self.history[user_id])
        return history[-n:] if n else history

    def get_recent_intent(self, user_id: str, n: int = 3) -> List[str]:
        history = self.get_history(user_id, n)
        return [turn.intent for turn in history]

    def get_context(self, user_id: str) -> Dict[str, Any]:
        history = self.get_history(user_id)

        context = {
            "recent_intents": [],
            "recent_skills": [],
            "recent_queries": [],
            "turn_count": len(history),
        }

        for turn in history:
            context["recent_intents"].append(turn.intent)
            context["recent_skills"].append(turn.skill_used)
            context["recent_queries"].append(turn.user_input)

        return context

    async def clear_history(self, user_id: str):
        if user_id in self.history:
            del self.history[user_id]
        if self._connected:
            try:
                await self._redis.delete(self._redis_key(user_id))
            except Exception as e:
                logger.warning("删除 Redis 对话历史失败", user_id=user_id, error=str(e))
        logger.info("清空对话历史", user_id=user_id)

    def has_history(self, user_id: str) -> bool:
        return user_id in self.history and len(self.history[user_id]) > 0


# 全局对话历史实例
dialogue_history = DialogueHistory(max_turns=10)
