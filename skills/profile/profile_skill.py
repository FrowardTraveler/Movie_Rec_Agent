"""
用户画像技能

管理和获取用户偏好信息
"""

from typing import Any, Dict

import structlog

from skills.base import BaseSkill

logger = structlog.get_logger()


class ProfileSkill(BaseSkill):
    """
    用户画像技能

    管理用户偏好，实现个性化推荐
    """

    name: str = "profile_skill"
    description: str = "管理用户偏好和画像信息"
    priority: int = 3

    # 模拟用户画像数据库（MVP）
    _user_profiles: Dict[str, Dict] = {}

    async def _execute(
        self, user_id: str, action: str = "get", preferences: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        执行用户画像管理

        Args:
            user_id: 用户 ID
            action: 操作类型 (get/update)
            preferences: 偏好信息

        Returns:
            用户画像信息
        """
        logger.info("执行用户画像管理", user_id=user_id, action=action)

        try:
            if action == "update" and preferences:
                return await self._update_profile(user_id, preferences)
            else:
                return await self._get_profile(user_id)

        except Exception as e:
            logger.error("用户画像管理失败", error=str(e))
            return {"success": False, "error": str(e), "skill": self.name}

    async def _get_profile(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户画像

        Args:
            user_id: 用户 ID

        Returns:
            用户画像
        """
        profile = self._user_profiles.get(user_id, self._create_default_profile(user_id))

        response = (
            f"你的观影偏好：\n\n"
            f"- 喜欢的类型: {', '.join(profile.get('preferred_genres', [])) or '未设置'}\n"
            f"- 喜欢的导演: {', '.join(profile.get('preferred_directors', [])) or '未设置'}\n"
            f"- 观影历史: {profile.get('watch_count', 0)} 部\n"
            f"- 平均评分偏好: {profile.get('avg_rating_preference', '未设置')}\n\n"
            f"你可以告诉我你喜欢什么类型的电影，我会根据你的偏好推荐~"
        )

        return {"success": True, "response": response, "data": profile, "skill": self.name}

    async def _update_profile(self, user_id: str, preferences: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新用户画像

        Args:
            user_id: 用户 ID
            preferences: 偏好信息

        Returns:
            更新后的用户画像
        """
        profile = self._user_profiles.get(user_id, self._create_default_profile(user_id))

        # 更新偏好
        if "genres" in preferences:
            existing = profile.get("preferred_genres", [])
            new_genres = list(set(existing + preferences["genres"]))
            profile["preferred_genres"] = new_genres

        if "directors" in preferences:
            existing = profile.get("preferred_directors", [])
            new_directors = list(set(existing + preferences["directors"]))
            profile["preferred_directors"] = new_directors

        if "rating" in preferences:
            profile["avg_rating_preference"] = preferences["rating"]

        profile["watch_count"] = profile.get("watch_count", 0) + 1

        self._user_profiles[user_id] = profile

        response = (
            f"好的，我已经记住你的偏好了！\n\n"
            f"你喜欢的类型: {', '.join(profile['preferred_genres'])}\n"
            f"我会根据你的偏好为你推荐电影~"
        )

        return {"success": True, "response": response, "data": profile, "skill": self.name}

    def _create_default_profile(self, user_id: str) -> Dict:
        """
        创建默认用户画像

        Args:
            user_id: 用户 ID

        Returns:
            默认画像
        """
        return {
            "user_id": user_id,
            "preferred_genres": [],
            "preferred_directors": [],
            "preferred_actors": [],
            "avg_rating_preference": None,
            "watch_count": 0,
            "last_watch_time": None,
        }
