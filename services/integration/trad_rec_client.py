"""
传统推荐系统集成客户端

封装对传统推荐系统的交互，让 Agent 能：
1. 调用传统推荐引擎获取推荐结果（HTTP）
2. 将用户偏好直接写入共享 Redis（两个系统共用同一个 Redis 实例）
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp
import redis.asyncio as aioredis
import structlog
from aiohttp import ClientTimeout

from agent.config.loader import ConfigLoader
from services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger()

# 加载 YAML 配置（支持环境变量覆盖）
_loader = ConfigLoader()
_yaml_config = _loader.load()

# Redis 连接配置
_redis_host = _yaml_config.get("redis", {}).get("host") or os.environ.get("REDIS_HOST", "localhost")
_REDIS_URL = f"redis://{_redis_host}:6379/0"

# 传统推荐系统地址
_trad_rec_url = _yaml_config.get("trad_rec", {}).get("base_url")
if not _trad_rec_url:
    _trad_rec_url = os.environ.get("TRAD_REC_BASE_URL", "http://localhost:8000")

# HTTP 请求超时设置（秒）
_HTTP_CONNECT_TIMEOUT = int(os.environ.get("TRAD_REC_CONNECT_TIMEOUT", "5"))
_HTTP_TOTAL_TIMEOUT = int(os.environ.get("TRAD_REC_TOTAL_TIMEOUT", "15"))

# 异步 Redis 客户端
try:
    redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
except Exception as e:
    logger.warning("Redis 连接失败", error=str(e))
    redis_client = None


@dataclass
class RecommendationItem:
    """推荐结果项"""

    movie_id: int
    title: str
    genres: List[str]
    score: float
    recall_type: Optional[str] = None
    poster_url: Optional[str] = None
    reason: Optional[str] = None


class TraditionalRecommendationClient:
    """
    传统推荐系统集成客户端

    负责：
    1. 调用传统推荐引擎获取推荐结果（HTTP 调用）
    2. 搜索电影获取真实 ID
    3. 将 Agent 分析出的用户偏好写入共享 Redis（两个系统共用）
    """

    def __init__(self, base_url: Optional[str] = None):
        # 优先使用传入参数，然后环境变量，最后使用配置文件
        self.base_url = base_url or _trad_rec_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        self._timeout = ClientTimeout(
            total=_HTTP_TOTAL_TIMEOUT,
            connect=_HTTP_CONNECT_TIMEOUT,
        )
        self._circuit_breaker = CircuitBreaker(
            name="trad_rec_client",
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=2,
            retry_attempts=2,
        )
        self._redis_circuit_breaker = CircuitBreaker(
            name="redis_user_profile", failure_threshold=5, recovery_timeout=60, success_threshold=1
        )

    async def initialize(self):
        """初始化 HTTP 客户端"""
        if not self._initialized:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._initialized = True
            logger.info(
                "传统推荐 API 客户端初始化完成", base_url=self.base_url, timeout=_HTTP_TOTAL_TIMEOUT
            )

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._session:
            await self._session.close()
            self._initialized = False
            logger.info("传统推荐 API 客户端已关闭")

    async def search_movie_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """
        通过电影名搜索获取真实电影信息（精确匹配优先）

        Args:
            title: 电影名称

        Returns:
            电影信息字典，包含 movie_id、title、genres 等
        """
        if not self._initialized:
            await self.initialize()

        # 传统推荐系统的路由：/api/search/movies/exact（后端没有 /v1 前缀）
        url = f"{self.base_url}/api/search/movies/exact"

        try:

            async def _do_search():
                async with self._session.get(url, params={"title": title, "limit": 5}) as response:
                    if response.status == 200:
                        results = await response.json()
                        if not results:
                            return None

                        # 策略：优先精确匹配（忽略大小写和标点）
                        import re

                        def normalize(t: str) -> str:
                            t = t.lower().strip()
                            t = re.sub(r"[^\w\s]", "", t)
                            t = re.sub(r"\s+", " ", t)
                            return t

                        query_norm = normalize(title)

                        for r in results:
                            if normalize(r.get("title", "")) == query_norm:
                                return r  # 精确匹配

                        # 没有精确匹配，返回第一个（最相关的）
                        return results[0]
                    else:
                        logger.warning("搜索 API 返回非 200 状态", status=response.status)
                    return None

            result = await self._circuit_breaker.call(_do_search)
            return result
        except CircuitBreakerOpenError:
            logger.warning("搜索服务已熔断，返回空结果", title=title)
            return None
        except Exception as e:
            logger.error("搜索电影失败", title=title, error=str(e))
            return None

    async def get_recommendations(
        self,
        user_id: Optional[str] = None,
        top_k: int = 10,
        hist_movie_ids: Optional[List[int]] = None,
        preferred_genres: Optional[List[str]] = None,
    ) -> List[RecommendationItem]:
        """
        调用传统推荐引擎获取个性化推荐

        Args:
            user_id: 用户ID
            top_k: 推荐数量
            hist_movie_ids: 用户历史观看记录
            preferred_genres: 偏好类型

        Returns:
            推荐电影列表
        """
        if not self._initialized:
            await self.initialize()

        # 传统推荐系统的路由：/api/recommendations/recommend（后端没有 /v1 前缀）
        url = f"{self.base_url}/api/recommendations/recommend"

        # 推荐 API 的请求体格式：UserFeaturesRequest
        payload = {}

        if user_id:
            try:
                payload["user_id"] = int(user_id)
            except (ValueError, TypeError):
                payload["user_id"] = None

        if hist_movie_ids:
            payload["hist_movie_ids"] = hist_movie_ids

        if preferred_genres:
            payload["preferred_genres"] = preferred_genres

        # top_k 是查询参数，不是请求体
        params = {"top_k": top_k}

        try:

            async def _do_recommend():
                async with self._session.post(url, json=payload, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        items = []
                        for item in data.get("items", []):
                            items.append(
                                RecommendationItem(
                                    movie_id=item["movie_id"],
                                    title=item["title"],
                                    genres=item.get("genres", []),
                                    score=item.get("score", 0.0),
                                    recall_type=item.get("recall_type"),
                                    poster_url=item.get("poster_url"),
                                )
                            )
                        logger.info(
                            "传统推荐成功",
                            user_id=user_id,
                            count=len(items),
                            strategy=data.get("ranking_strategy", "unknown"),
                        )
                        return items
                    else:
                        logger.warning("传统推荐 API 返回非 200 状态", status=response.status)
                        return []

            result = await self._circuit_breaker.call(_do_recommend)
            return result
        except CircuitBreakerOpenError:
            logger.warning("传统推荐服务已熔断，返回空结果", user_id=user_id)
            return []
        except Exception as e:
            logger.error("调用传统推荐 API 失败", error=str(e))
            return []

    async def resolve_llm_movie_ids(self, llm_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将 LLM 生成的假 movie_id 替换为数据库中真实的 ID

        通过精确标题搜索获取真实 ID

        Args:
            llm_items: LLM 生成的推荐项列表

        Returns:
            修正后的推荐项列表
        """
        resolved_items = []

        for item in llm_items:
            title = item.get("title", "")
            if not title:
                logger.warning("跳过空标题的电影")
                continue

            # 尝试多次搜索策略：
            # 1. 使用完整标题精确搜索
            # 2. 如果包含英文名（如 "寄生虫 Parasite"），尝试拆分搜索
            # 3. 回退到模糊搜索

            movie_info = await self.search_movie_by_title(title)

            # 如果精确搜索失败，尝试拆分标题（处理 "寄生虫 Parasite" 这样的格式）
            if not movie_info and (" " in title or "/" in title):
                # 尝试第一个词（通常是中文名）
                parts = title.replace("/", " ").split()
                if parts:
                    first_part = parts[0].strip()
                    if first_part:
                        logger.info("精确搜索失败，尝试搜索", query=first_part, original=title)
                        movie_info = await self.search_movie_by_title(first_part)

            if movie_info:
                # 验证搜索结果：检查标题是否相似
                found_title = movie_info.get("title", "")
                resolved_item = {
                    "movie_id": movie_info.get("movie_id", 0),
                    "title": found_title,  # 使用数据库中的标题
                    "genres": movie_info.get("genres", []),
                    "score": movie_info.get("imdb_rating", item.get("score", 0.0)),
                    "poster_url": "",
                    "reason": item.get("reason", ""),
                    "source": "llm_fallback_resolved",
                }
                resolved_items.append(resolved_item)
                logger.info(
                    "找到电影",
                    original=title,
                    resolved=found_title,
                    movie_id=movie_info.get("movie_id"),
                )
            else:
                logger.warning("未找到电影，跳过", title=title)

        return resolved_items

    async def update_user_profile(
        self,
        user_id: str,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        movie_ids: Optional[List[int]] = None,
    ) -> bool:
        """
        将 Agent 分析出的用户偏好异步写入共享 Redis

        两个系统共用同一个 Redis 实例，这样传统推荐系统可以直接读取 Agent 记录的偏好

        Args:
            user_id: 用户ID
            genre: 电影类型偏好
            mood: 心情/场景
            movie_ids: 相关电影ID列表

        Returns:
            是否成功
        """
        if not redis_client:
            logger.warning("Redis 未连接，无法更新用户偏好")
            return False

        try:

            async def _do_update():
                profile_key = f"user:{user_id}:profile"

                pipeline = redis_client.pipeline()

                # 更新 genre 偏好
                if genre:
                    existing_genres = await redis_client.hget(profile_key, "frequent_genres")
                    if existing_genres:
                        genre_list = existing_genres.split(",")
                        if genre not in genre_list:
                            genre_list.append(genre)
                        pipeline.hset(profile_key, "frequent_genres", ",".join(genre_list))
                    else:
                        pipeline.hset(profile_key, "frequent_genres", genre)

                # 更新 mood 偏好
                if mood:
                    pipeline.hset(profile_key, "last_mood", mood)

                # 记录最近交互的电影
                if movie_ids:
                    pipeline.hset(profile_key, "last_interacted_movies", json.dumps(movie_ids))

                if pipeline.command_stack:
                    await pipeline.execute()

                logger.info("用户偏好已更新（Redis）", user_id=user_id, genre=genre, mood=mood)
                return True

            result = await self._redis_circuit_breaker.call(_do_update)
            return result
        except CircuitBreakerOpenError:
            logger.warning("Redis 更新已熔断，跳过用户偏好更新", user_id=user_id)
            return False
        except Exception as e:
            logger.error("更新用户偏好失败（Redis）", user_id=user_id, error=str(e))
            return False

    async def health_check(self) -> bool:
        """检查传统推荐服务是否可用"""
        if not self._initialized:
            await self.initialize()

        url = f"{self.base_url}/api/recommendations/health"

        try:
            async with self._session.get(url) as response:
                return response.status == 200
        except Exception as e:
            logger.warning("传统推荐服务健康检查失败", error=str(e))
            return False


trad_rec_client = TraditionalRecommendationClient()
