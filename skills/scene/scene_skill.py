"""
场景推荐技能

根据特定场景（约会、独处、聚会等）推荐电影
"""

from typing import Any, Dict

import structlog

from skills.base import BaseSkill

logger = structlog.get_logger()


class SceneSkill(BaseSkill):
    """
    场景推荐技能

    根据场景需求推荐适合的电影
    """

    name: str = "scene_skill"
    description: str = "根据场景（约会、独处、聚会等）推荐电影"
    priority: int = 2

    # 场景推荐映射
    scene_recommendations = {
        "date": {"genres": ["爱情", "浪漫"], "response": "约会适合看浪漫温馨的爱情电影~"},
        "alone": {"genres": ["剧情", "科幻", "悬疑"], "response": "独处时适合看一些有深度的电影~"},
        "party": {"genres": ["喜剧", "动作"], "response": "聚会适合看轻松欢乐的电影~"},
        "relax": {"genres": ["喜剧", "治愈"], "response": "放松时适合看轻松治愈的电影~"},
        "learn": {"genres": ["纪录片", "剧情"], "response": "学习时适合看有教育意义的电影~"},
    }

    # 中文场景关键词映射
    scene_keywords = {
        "date": ["约会", "情侣", "恋爱", "浪漫"],
        "alone": ["独处", "一个人", "独自"],
        "party": ["聚会", "派对", "朋友一起", "热闹"],
        "relax": ["放松", "休闲", "解压", "开心"],
        "learn": ["学习", "教育", "知识", "成长"],
    }

    async def _execute(self, scene: str, user_id: str = None, top_k: int = 5) -> Dict[str, Any]:
        """
        执行场景推荐

        Args:
            scene: 场景类型（中文描述）
            user_id: 用户 ID
            top_k: 推荐数量

        Returns:
            场景推荐结果
        """
        logger.info("执行场景推荐", scene=scene, user_id=user_id)

        # 匹配场景（通过中文关键词）
        matched_scene = self._match_scene(scene)

        if not matched_scene:
            return {
                "success": True,
                "response": "你可以告诉我你现在的场景，比如：约会、独处、聚会、放松、学习，我会为你推荐合适的电影~",
                "skill": self.name,
            }

        scene_info = self.scene_recommendations[matched_scene]
        scene_name = self._get_scene_name(matched_scene)

        response = (
            f"{scene_info['response']}\n\n"
            f"为你推荐以下适合 **{scene_name}** 场景的电影：\n"
            f"- 类型偏好: {', '.join(scene_info['genres'])}\n"
            f"- 推荐数量: {top_k} 部\n\n"
            f"希望这些电影能陪伴你度过美好时光！"
        )

        return {
            "success": True,
            "response": response,
            "data": {"scene": matched_scene, "genres": scene_info["genres"], "top_k": top_k},
            "skill": self.name,
        }

    def _match_scene(self, query: str) -> str:
        """
        匹配场景关键词

        Args:
            query: 用户输入

        Returns:
            场景类型（英文）
        """
        for scene_key, keywords in self.scene_keywords.items():
            for keyword in keywords:
                if keyword in query:
                    return scene_key
        return ""

    def _get_scene_name(self, scene_key: str) -> str:
        """
        获取场景中文名称

        Args:
            scene_key: 场景英文键

        Returns:
            场景中文名
        """
        name_map = {
            "date": "约会",
            "alone": "独处",
            "party": "聚会",
            "relax": "放松",
            "learn": "学习",
        }
        return name_map.get(scene_key, scene_key)
