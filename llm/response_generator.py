"""
LLM 响应生成器

使用 LLM 生成智能、自然的回答，而非预设定模板
"""

from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()


class LLMResponseGenerator:
    """
    LLM 响应生成器

    根据上下文和用户查询，生成个性化的自然语言回答
    """

    def __init__(self, llm_router=None):
        """
        初始化响应生成器

        Args:
            llm_router: LLM 路由器实例
        """
        self.llm_router = llm_router

    async def generate_recommend_response(
        self, user_input: str, movies: List[Dict[str, Any]], user_context: Dict[str, Any] = None
    ) -> str:
        """
        生成推荐回复

        Args:
            user_input: 用户原始输入
            movies: 推荐的电影列表
            user_context: 用户上下文（偏好、历史等）

        Returns:
            生成的回复文本
        """
        if not movies:
            return "抱歉，我暂时没有为你找到合适的电影推荐。你可以尝试告诉我你喜欢的类型或导演，我会更好地为你推荐~"

        # 构建推荐上下文
        context = self._build_recommend_context(movies, user_context)

        # 如果有 LLM，使用 LLM 生成
        if self.llm_router and self.llm_router._initialized:
            try:
                prompt = self._build_recommend_prompt(user_input, context)
                response = await self.llm_router.generate(prompt, max_tokens=500)
                return response
            except Exception as e:
                logger.warning("LLM 生成失败，使用降级方案", error=str(e))

        # 降级方案：智能模板 + 上下文
        return self._generate_fallback_recommend_response(user_input, movies, context)

    def _build_recommend_context(self, movies: List[Dict], user_context: Dict = None) -> str:
        """构建推荐上下文"""
        context_parts = []

        for i, movie in enumerate(movies, 1):
            title = movie.get("title", "未知")
            year = movie.get("year", "")
            genres = movie.get("genres", "未知")
            rating = movie.get("rating", "N/A")
            director = movie.get("director", "未知")
            overview = movie.get("overview", "")

            context_parts.append(
                f"{i}. 《{title}》({year})\n"
                f"   类型: {genres} | 评分: {rating} | 导演: {director}\n"
                f"   简介: {overview}"
            )

        return "\n\n".join(context_parts)

    def _build_recommend_prompt(self, user_input: str, context: str) -> str:
        """
        构建推荐提示词

        Args:
            user_input: 用户输入
            context: 推荐上下文

        Returns:
            提示词
        """
        prompt = f"""你是一个专业的电影推荐助手。用户提出了以下需求：

用户需求：{user_input}

根据这个需求，我为以下电影进行了推荐：

{context}

请根据这些信息，生成一个自然、有说服力的推荐回复。要求：
1. 开头要亲切自然，回应用户的需求
2. 对每部电影进行简短的推荐理由（1-2句话）
3. 突出电影的亮点和为什么适合用户
4. 结尾可以询问用户是否需要更多推荐或了解某部电影的详情
5. 使用中文回答
6. 语气要像朋友间的推荐，不要太正式"""

        return prompt

    def _generate_fallback_recommend_response(
        self, user_input: str, movies: List[Dict], context: str
    ) -> str:
        """
        降级推荐回复（当 LLM 不可用时）

        使用智能模板，但仍然基于真实数据
        """
        user_input_lower = user_input.lower()

        # 根据用户输入选择合适的开场白
        if any(kw in user_input_lower for kw in ["心情", "难过", "不开心", "低落"]):
            greeting = "看到你心情不太好，我来为你推荐几部治愈系的电影，希望能让你开心一些~ 🎬"
        elif any(kw in user_input_lower for kw in ["开心", "高兴", "棒"]):
            greeting = "心情好的时候看电影更棒呢！我为你精选了几部电影，一起来看看吧~ 🎉"
        elif any(kw in user_input_lower for kw in ["约会", "情侣", "恋爱"]):
            greeting = "约会看电影是个不错的选择！我为你推荐了几部适合一起观看的电影~ 💕"
        elif any(kw in user_input_lower for kw in ["推荐", "介绍", "想看"]):
            greeting = "好的！根据我的了解，我为你精心挑选了以下几部电影："
        else:
            greeting = "为你推荐以下几部精彩的电影：🎬"

        # 构建电影列表
        movie_lines = []
        for i, movie in enumerate(movies[:5], 1):
            title = movie.get("title", "未知")
            year = movie.get("year", "")
            genres = movie.get("genres", "未知")
            rating = movie.get("rating", "N/A")
            director = movie.get("director", "未知")
            overview = movie.get("overview", "")[:60]

            # 生成推荐理由
            reason = self._generate_recommend_reason(movie, user_input_lower)

            movie_lines.append(
                f"{i}. **《{title}》** ({year})\n"
                f"   🎭 类型: {genres} | ⭐ 评分: {rating} | 🎬 导演: {director}\n"
                f"   📖 {overview}...\n"
                f"   💡 {reason}\n"
            )

        # 结尾
        closing = "\n".join(
            [
                "以上是我为你精心推荐的电影！你可以：",
                "• 告诉我你对哪部感兴趣，我可以详细介绍",
                "• 告诉我你的偏好，我为你做更精准的推荐",
                "• 搜索特定电影，如'搜索复仇者联盟'",
            ]
        )

        return f"{greeting}\n\n" + "\n".join(movie_lines) + f"\n{closing}"

    def _generate_recommend_reason(self, movie: Dict, user_input: str) -> str:
        """
        根据电影和用户输入生成推荐理由

        Args:
            movie: 电影信息
            user_input: 用户输入

        Returns:
            推荐理由
        """
        rating = movie.get("rating", 0)
        genres = movie.get("genres", "")
        title = movie.get("title", "")

        reasons = []

        # 基于评分
        if rating >= 9.0:
            reasons.append("评分超高，必看经典")
        elif rating >= 8.5:
            reasons.append("口碑非常好，值得一看")
        elif rating >= 8.0:
            reasons.append("评价很高，值得推荐")

        # 基于类型匹配用户输入
        if "科幻" in genres and "科幻" in user_input:
            reasons.append("正是你喜欢的科幻类型")
        elif "爱情" in genres and any(kw in user_input for kw in ["爱情", "浪漫", "约会"]):
            reasons.append("浪漫的爱情故事很适合")
        elif "喜剧" in genres and any(kw in user_input for kw in ["开心", "笑", "轻松"]):
            reasons.append("轻松幽默，能让你开心")
        elif "动作" in genres and "动作" in user_input:
            reasons.append("刺激的动作场面")

        # 默认推荐理由
        if not reasons:
            default_reasons = [
                "剧情精彩，不容错过",
                "深受观众喜爱",
                "值得反复品味的好电影",
                "故事引人入胜",
            ]
            import random

            reasons.append(random.choice(default_reasons))

        return "，".join(reasons[:2])  # 最多两个理由

    async def generate_knowledge_response(
        self, user_input: str, movie_info: Dict[str, Any], question_type: str
    ) -> str:
        """
        生成知识问答回复

        Args:
            user_input: 用户问题
            movie_info: 电影信息
            question_type: 问题类型

        Returns:
            生成的回复
        """
        # 始终使用 LLM 生成回答（即使本地数据库没有信息）
        if self.llm_router and self.llm_router._initialized:
            try:
                prompt = self._build_knowledge_prompt(user_input, movie_info, question_type)
                response = await self.llm_router.generate(prompt, max_tokens=500)
                return response
            except Exception as e:
                logger.warning("LLM 生成失败，使用降级方案", error=str(e))

        return self._generate_fallback_knowledge_response(user_input, movie_info, question_type)

    def _build_knowledge_prompt(self, user_input: str, movie_info: Dict, question_type: str) -> str:
        """构建知识问答提示词"""
        # 检查电影信息是否完整
        has_full_info = all(
            [
                movie_info.get("title") != "未知",
                movie_info.get("director") != "未知",
                movie_info.get("year") != "未知",
                movie_info.get("genres") != "未知",
            ]
        )

        if has_full_info:
            # 有完整信息，基于信息回答
            prompt = f"""你是一个电影知识助手。用户问了以下问题：

用户问题：{user_input}

电影信息：
- 名称：{movie_info.get("title", "未知")}
- 年份：{movie_info.get("year", "未知")}
- 类型：{movie_info.get("genres", "未知")}
- 评分：{movie_info.get("rating", "未知")}
- 导演：{movie_info.get("director", "未知")}
- 简介：{movie_info.get("overview", "未知")}

问题类型：{question_type}

请根据这些信息，用自然、友好的语气回答用户的问题。要求：
1. 直接回答用户的问题
2. 可以适当补充相关背景信息
3. 使用中文回答
4. 语气像朋友聊天"""
        else:
            # 信息不完整，让LLM使用自己的知识回答
            prompt = f"""你是一个电影知识助手。用户问了以下问题：

用户问题：{user_input}

问题类型：{question_type}

注意：我的本地数据库中没有这部电影的详细信息，但你应该根据你的训练知识来回答这个问题。

请根据你自己的电影知识，用自然、友好的语气回答用户的问题。要求：
1. 直接回答用户的问题（如果知道答案的话）
2. 可以提供导演、演员、剧情、评分等相关信息
3. 如果不确定某些细节，可以诚实地说明
4. 使用中文回答
5. 语气像朋友聊天，不要过于正式
6. 如果完全不知道，可以建议用户尝试搜索其他电影"""

        return prompt

    def _generate_fallback_knowledge_response(
        self, user_input: str, movie_info: Dict, question_type: str
    ) -> str:
        """降级知识问答回复"""
        title = movie_info.get("title", "未知")

        # 如果电影信息不完整，返回更友好的提示
        if title == "未知" or movie_info.get("director") == "未知":
            return (
                f"关于你的问题：'{user_input}'\n\n"
                f"我暂时没有找到相关的电影信息。不过别担心！你可以：\n"
                f"• 告诉我具体的电影名称，我来帮你查找\n"
                f"• 尝试搜索其他电影的问题"
            )

        if question_type == "director":
            director = movie_info.get("director", "未知")
            year = movie_info.get("year", "")
            genres = movie_info.get("genres", "")
            if director != "未知":
                return f"《{title}》的导演是 **{director}**。这部电影于 {year} 年上映，是一部{genres}类型的佳作。"

        elif question_type == "rating":
            rating = movie_info.get("rating", "未知")
            if rating != "未知":
                return f"《{title}》的评分是 **{rating} 分**。" + (
                    "这是一部口碑非常好的经典之作！"
                    if float(rating) >= 8.5
                    else "这是一部值得一看的电影！"
                    if float(rating) >= 7.5
                    else "这部电影也有其独特的魅力。"
                )

        elif question_type == "plot":
            overview = movie_info.get("overview", "暂无简介")
            if overview != "暂无简介":
                return f"《{title}》的剧情简介：{overview}"

        elif question_type == "year":
            year = movie_info.get("year", "未知")
            if year != "未知":
                return f"《{title}》于 **{year} 年**上映。"

        elif question_type == "genre":
            genres = movie_info.get("genres", "未知")
            if genres != "未知":
                return f"《{title}》的类型是 **{genres}**。"

        # 通用回答
        if movie_info.get("director") != "未知":
            return (
                f"关于《{title}》，我知道以下信息：\n\n"
                f"- 导演: {movie_info.get('director', '未知')}\n"
                f"- 年份: {movie_info.get('year', '未知')}\n"
                f"- 类型: {movie_info.get('genres', '未知')}\n"
                f"- 评分: {movie_info.get('rating', '未知')}\n"
                f"- 简介: {movie_info.get('overview', '暂无')[:100]}\n\n"
                f"如果你想了解更多细节，可以继续问我~"
            )
        else:
            return (
                f"关于你的问题，我暂时没有找到《{title}》的详细信息。\n"
                f"你可以尝试问我其他电影，或者告诉我更多线索，我会尽力帮你找到~"
            )


# 全局响应生成器实例
response_generator = LLMResponseGenerator()
