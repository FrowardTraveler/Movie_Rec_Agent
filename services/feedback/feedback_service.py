"""
用户反馈服务

收集推荐结果的评分、点赞/踩等反馈数据
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

import structlog
from services.dialogue.dialogue_history import dialogue_history

logger = structlog.get_logger()


@dataclass
class FeedbackRecord:
    """反馈记录"""
    user_id: str
    query: str
    recommended_movie_ids: List[int]
    rated_movie_id: Optional[int]  # 用户评分的电影
    rating: int  # 1-5 分，1=踩，3=一般，5=赞
    feedback_type: str  # "explicit" 显式评分, "implicit" 隐式行为
    timestamp: float
    session_id: Optional[str] = None


class FeedbackService:
    """
    用户反馈服务
    
    负责：
    1. 收集用户对推荐结果的反馈
    2. 存储反馈记录到 Redis
    3. 提供用户偏好分析数据
    """
    
    FEEDBACK_KEY_PREFIX = "agent:feedback:"
    USER_PROFILE_PREFIX = "agent:profile:"
    
    def __init__(self):
        self._redis_client = None
    
    async def initialize(self):
        """初始化 Redis 连接"""
        self._redis_client = dialogue_history._redis
        if not self._redis_client:
            await dialogue_history.initialize()
            self._redis_client = dialogue_history._redis
        
        # 确保使用 utf-8 编码
        if hasattr(self._redis_client, 'encoding'):
            self._redis_client.encoding = 'utf-8'
    
    async def submit_feedback(self, feedback: Dict[str, Any]) -> bool:
        """
        提交反馈
        
        Args:
            feedback: 反馈数据，包含：
                - user_id: 用户 ID
                - query: 原始查询
                - recommended_movie_ids: 推荐的电影 ID 列表
                - rated_movie_id: 评分的电影 ID
                - rating: 评分 (1-5)
                - feedback_type: explicit 或 implicit
                
        Returns:
            是否提交成功
        """
        try:
            if not self._redis_client:
                await self.initialize()
            
            import json
            feedback_data = {
                "user_id": feedback["user_id"],
                "query": feedback.get("query", ""),
                "recommended_movie_ids": feedback.get("recommended_movie_ids", []),
                "rated_movie_id": feedback.get("rated_movie_id"),
                "rating": int(feedback["rating"]),
                "feedback_type": feedback.get("feedback_type", "explicit"),
                "timestamp": time.time(),
            }
            
            import json
            pipe = self._redis_client.pipeline()
            pipe.rpush(f"{self.FEEDBACK_KEY_PREFIX}all", json.dumps(feedback_data, ensure_ascii=False))
            pipe.rpush(f"{self.FEEDBACK_KEY_PREFIX}user:{feedback_data['user_id']}", json.dumps(feedback_data, ensure_ascii=False))
            pipe.ltrim(f"{self.FEEDBACK_KEY_PREFIX}all", -1000, -1)  # 保留最近 1000 条
            pipe.ltrim(f"{self.FEEDBACK_KEY_PREFIX}user:{feedback_data['user_id']}", -1000, -1)
            await pipe.execute()
            
            # 更新用户画像
            await self._update_user_profile(feedback_data["user_id"], feedback_data["rated_movie_id"], feedback_data["rating"])
            
            logger.info("反馈已提交", user_id=feedback_data["user_id"], rating=feedback_data["rating"])
            return True
            
        except Exception as e:
            logger.error("提交反馈失败", error=str(e))
            return False
    
    async def _update_user_profile(self, user_id: str, movie_id: Optional[int], rating: int):
        """
        更新用户画像
        
        根据反馈调整用户偏好
        """
        if not movie_id:
            return
        
        try:
            profile_key = f"{self.USER_PROFILE_PREFIX}{user_id}"
            
            # 获取当前评分数据
            current = await self._redis_client.hgetall(profile_key)
            total_ratings = int(current.get("total_ratings", 0)) + 1
            avg_rating = float(current.get("avg_rating", 0))
            new_avg = (avg_rating * (total_ratings - 1) + rating) / total_ratings
            
            # 使用同一个 pipeline 执行所有操作
            pipe = self._redis_client.pipeline()
            
            # 记录喜欢的电影
            if rating >= 4:
                pipe.zincrby(f"{profile_key}:liked_movies", 1.0, str(movie_id))
            # 记录不喜欢的电影
            elif rating <= 2:
                pipe.zincrby(f"{profile_key}:disliked_movies", 1.0, str(movie_id))
            
            # 更新用户统计数据
            pipe.hset(profile_key, mapping={
                "total_ratings": total_ratings,
                "avg_rating": round(new_avg, 2),
                "last_feedback_time": time.time(),
            })
            
            await pipe.execute()
            
        except Exception as e:
            logger.warning("更新用户画像失败", user_id=user_id, error=str(e))
    
    async def get_user_feedback(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取用户的反馈历史"""
        try:
            if not self._redis_client:
                await self.initialize()
            
            import json
            data = await self._redis_client.lrange(
                f"{self.FEEDBACK_KEY_PREFIX}user:{user_id}", 
                -limit, 
                -1
            )
            return [json.loads(item) for item in data]
        except Exception as e:
            logger.error("获取反馈历史失败", error=str(e))
            return []
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """获取用户画像"""
        try:
            if not self._redis_client:
                await self.initialize()
            
            profile_key = f"{self.USER_PROFILE_PREFIX}{user_id}"
            data = await self._redis_client.hgetall(profile_key)
            
            # 获取喜欢的电影
            liked = await self._redis_client.zrevrange(
                f"{profile_key}:liked_movies", 0, 19, withscores=True
            )
            disliked = await self._redis_client.zrevrange(
                f"{profile_key}:disliked_movies", 0, 9, withscores=True
            )
            
            return {
                "user_id": user_id,
                "total_ratings": int(data.get("total_ratings", 0)),
                "avg_rating": float(data.get("avg_rating", 0)),
                "last_feedback_time": float(data.get("last_feedback_time", 0)),
                "top_liked": [{"movie_id": m, "count": s} for m, s in liked],
                "top_disliked": [{"movie_id": m, "count": s} for m, s in disliked],
            }
        except Exception as e:
            logger.error("获取用户画像失败", error=str(e))
            return {"user_id": user_id}


# 全局实例
feedback_service = FeedbackService()
