"""
推荐引擎适配层

封装现有推荐系统，提供统一的接口
"""

import asyncio
import importlib.util
import sys
from typing import Any, Dict, List, Optional

from agent.config.agent_config import config


class RecommendationEngineAdapter:
    """
    推荐引擎适配器

    封装现有的推荐系统，提供统一的接口
    """

    def __init__(self):
        """
        初始化推荐引擎适配器

        动态导入现有的推荐系统模块
        """
        self.config = config.recommendation
        self._engine = None
        self._initialized = False

    async def initialize(self):
        """
        初始化推荐引擎

        动态加载现有推荐系统模块
        """
        if self._initialized:
            return

        try:
            # 尝试导入现有的推荐系统模块
            # 注意：这里只是模拟导入，实际环境中需要根据现有项目结构调整
            engine_path = self.config.engine_path

            # 动态导入现有推荐系统
            spec = importlib.util.spec_from_file_location(
                "existing_recommendation", f"{engine_path}/online/pipeline.py"
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules["existing_recommendation"] = module
                spec.loader.exec_module(module)

                # 获取推荐流水线
                self._engine = module.get_pipeline() if hasattr(module, "get_pipeline") else None

            self._initialized = True
            print(f"推荐引擎已初始化: {self._engine is not None}")

        except Exception as e:
            print(f"初始化推荐引擎失败: {e}")
            # 如果无法导入现有系统，则使用模拟实现
            self._engine = MockRecommendationEngine()
            self._initialized = True

    async def get_recommendations(
        self, user_id: str, context: Optional[Dict] = None, top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取推荐结果

        Args:
            user_id: 用户 ID
            context: 上下文信息 (心情、场景、偏好等)
            top_k: 推荐数量

        Returns:
            推荐电影列表
        """
        if not self._initialized:
            await self.initialize()

        if top_k is None:
            top_k = self.config.final_top_k

        # 构建用户特征
        user_features = await self._build_user_features(user_id, context)

        try:
            # 调用推荐引擎
            if self._engine:
                # 如果有现有引擎，使用它
                recommendations = await self._call_existing_engine(user_features, context, top_k)
            else:
                # 否则使用模拟实现
                recommendations = await self._mock_recommendations(user_id, context, top_k)

            return recommendations

        except Exception as e:
            print(f"推荐引擎调用失败: {e}")
            # 失败时返回模拟推荐
            return await self._fallback_recommendations(user_id, top_k)

    async def _build_user_features(self, user_id: str, context: Optional[Dict]) -> Dict:
        """
        构建用户特征

        Args:
            user_id: 用户 ID
            context: 上下文信息

        Returns:
            用户特征字典
        """
        features = {
            "user_id": user_id,
            "context": context or {},
            "timestamp": asyncio.get_event_loop().time(),
        }

        # 这里可以添加更复杂的特征工程逻辑
        # 例如：用户画像、历史行为、偏好标签等

        return features

    async def _call_existing_engine(
        self, user_features: Dict, context: Optional[Dict], top_k: int
    ) -> List[Dict[str, Any]]:
        """
        调用现有的推荐引擎

        Args:
            user_features: 用户特征
            context: 上下文信息
            top_k: 推荐数量

        Returns:
            推荐结果
        """
        # 这里是模拟调用现有推荐系统的接口
        # 实际实现需要根据现有项目的 API 调整
        try:
            # 模拟现有推荐系统的调用
            result = await self._engine.recommend(user_features, top_k=top_k)
            return result
        except Exception as e:
            print(f"调用现有推荐引擎失败: {e}")
            return await self._mock_recommendations(
                user_features.get("user_id", "unknown"), context, top_k
            )

    async def _mock_recommendations(
        self, user_id: str, context: Optional[Dict], top_k: int
    ) -> List[Dict[str, Any]]:
        """
        模拟推荐结果（用于 MVP 阶段）

        Args:
            user_id: 用户 ID
            context: 上下文信息
            top_k: 推荐数量

        Returns:
            模拟推荐结果
        """
        # 根据上下文生成相关的推荐
        movies = [
            {
                "id": f"movie_{i}",
                "title": f"推荐电影 {i}",
                "genres": ["动作", "科幻", "悬疑"][i % 3],
                "year": 2020 + (i % 5),
                "rating": round(7.0 + (i % 3), 1),
                "poster": f"https://example.com/poster_{i}.jpg",
                "overview": f"这是一部精彩的电影 {i}，值得一看！",
                "similarity_score": round(0.8 + (i * 0.05), 2),
            }
            for i in range(1, top_k + 1)
        ]

        # 根据上下文调整推荐
        if context:
            scene = context.get("scene", "").lower()
            mood = context.get("mood", "").lower()

            for movie in movies:
                if "浪漫" in scene or "约会" in scene:
                    movie["genres"] = "爱情"
                    movie["title"] = f"浪漫电影 {movie['id'][-1]}"
                elif "轻松" in mood or "开心" in mood:
                    movie["genres"] = "喜剧"
                    movie["title"] = f"欢乐电影 {movie['id'][-1]}"

        return movies

    async def _fallback_recommendations(self, user_id: str, top_k: int) -> List[Dict[str, Any]]:
        """
        降级推荐（当推荐引擎失败时使用）

        Args:
            user_id: 用户 ID
            top_k: 推荐数量

        Returns:
            降级推荐结果
        """
        # 返回热门电影作为降级方案
        popular_movies = [
            {
                "id": f"popular_{i}",
                "title": f"热门电影 {i}",
                "genres": ["剧情", "动作", "喜剧"][i % 3],
                "year": 2023,
                "rating": 8.5 - (i * 0.2),
                "poster": f"https://example.com/popular_{i}.jpg",
                "overview": f"这是一部非常受欢迎的电影 {i}！",
                "similarity_score": 0.9,
            }
            for i in range(1, top_k + 1)
        ]

        return popular_movies


class MockRecommendationEngine:
    """
    模拟推荐引擎（用于 MVP 阶段）

    当无法导入现有推荐系统时使用
    """

    async def recommend(self, user_features: Dict, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        模拟推荐方法

        Args:
            user_features: 用户特征
            top_k: 推荐数量

        Returns:
            模拟推荐结果
        """
        await asyncio.sleep(0.1)  # 模拟计算时间

        movies = [
            {
                "id": f"mock_{i}",
                "title": f"模拟推荐电影 {i}",
                "genres": ["科幻", "动作", "剧情"][i % 3],
                "year": 2022 + (i % 3),
                "rating": round(7.5 + (i * 0.1), 1),
                "poster": f"https://example.com/mock_{i}.jpg",
                "overview": f"这是模拟推荐的电影 {i}，具有出色的视觉效果和剧情。",
                "similarity_score": round(0.85 + (i * 0.02), 2),
            }
            for i in range(1, top_k + 1)
        ]

        return movies


# 全局推荐引擎实例
recommendation_engine = RecommendationEngineAdapter()
