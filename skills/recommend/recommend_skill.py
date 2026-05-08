"""
推荐技能

处理用户的推荐请求，使用推荐引擎适配器
"""

from typing import Any, Dict

import structlog

from services.recommendation.engine_adapter import recommendation_engine
from skills.base import BaseSkill

logger = structlog.get_logger()


class RecommendSkill(BaseSkill):
    """
    推荐技能

    调用推荐引擎适配器，返回个性化推荐结果
    """

    name: str = "recommend_skill"
    description: str = "推荐电影"
    priority: int = 1

    async def _execute(
        self, user_id: str, context: Dict[str, Any], top_k: int = 10, **kwargs
    ) -> Dict[str, Any]:
        """
        执行推荐

        Args:
            user_id: 用户 ID
            context: 上下文信息，包含查询、心情、场景等
            top_k: 推荐数量

        Returns:
            推荐结果
        """
        query = context.get("query", "推荐几部电影")
        logger.info("执行推荐技能", user_id=user_id, query=query, top_k=top_k)

        try:
            # 调用推荐引擎适配器
            recommendations = await recommendation_engine.get_recommendations(
                user_id=user_id, context=context, top_k=top_k
            )

            return {
                "success": True,
                "data": {
                    "items": recommendations,
                    "count": len(recommendations) if recommendations else 0,
                    "mode": "engine_adapter",
                },
                "skill": self.name,
            }

        except Exception as e:
            logger.error("推荐技能执行失败", error=str(e))
            return {"success": False, "error": str(e), "skill": self.name}
