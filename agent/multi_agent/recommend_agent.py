"""
推荐Agent - 电影推荐专家

流程：LLM 生成推荐 → 逐一到 RAG 数据库检索验证 → 存在的保留 → 全部找不到才用 LLM 原始结果
"""

import json
from typing import Any, Dict, List

import structlog

from agent.multi_agent import BaseAgent, MultiAgentState
from services.integration.trad_rec_client import trad_rec_client

logger = structlog.get_logger()


class RecommendAgent(BaseAgent):
    """
    推荐Agent - 电影推荐专家

    职责：
    - LLM 自由生成推荐电影
    - 逐一到传统系统搜索接口验证是否存在
    - 存在的保留（使用真实 movie_id 和 poster_url），不存在的跳过
    - 全部找不到时，用 LLM 原始结果兜底
    """

    name: str = "recommend_agent"
    description: str = "电影推荐专家 - LLM 生成 + 传统系统搜索验证"

    def __init__(self, llm_router=None):
        super().__init__(llm_router)

    async def initialize(self):
        """初始化推荐Agent"""
        if self._initialized:
            return

        self._initialized = True
        logger.info("推荐Agent初始化完成")

    async def execute(self, state: MultiAgentState) -> MultiAgentState:
        """执行推荐任务"""
        try:
            logger.info("[RecommendAgent] 开始执行")
            logger.info(f"   用户输入: {state['user_input']}")
            logger.info(f"   用户ID: {state['user_id']}")

            intent_analysis = state.get("intent_analysis", {})
            extracted_info = intent_analysis.get("extracted_info", {})

            genre = extracted_info.get("genre", "")
            mood = extracted_info.get("mood", "")
            year = extracted_info.get("year", "")
            other = extracted_info.get("other", "")
            use_traditional = extracted_info.get("use_traditional", False)

            logger.info(f"   [偏好] 类型: {genre}, 心情: {mood}, 年份: {year}, 其他: {other}")

            if use_traditional:
                logger.info("   [降级方案] 使用传统推荐系统...")
                result = await self._get_traditional_recommendation(state, extracted_info)
                state["agent_results"].append(result)
                return state

            # 步骤 1: LLM 生成推荐
            logger.info("   [步骤1] LLM 生成推荐电影...")
            llm_result = await self._generate_with_llm(state, extracted_info)

            if (
                not llm_result["success"]
                or not llm_result["data"]
                or not llm_result["data"].get("items")
            ):
                logger.warning("   [LLM生成] LLM 未能生成推荐，尝试传统推荐降级...")
                result = await self._get_traditional_recommendation(state, extracted_info)
                state["agent_results"].append(result)
                return state

            llm_items = llm_result["data"]["items"]
            logger.info(f"   [LLM生成] LLM 推荐了 {len(llm_items)} 部电影")
            for item in llm_items:
                logger.info(
                    f"      - {item.get('title_zh', item.get('title', 'unknown'))} ({item.get('title_en', 'N/A')})"
                )

            # 步骤 2: 用英文片名到传统系统搜索验证
            logger.info("   [步骤2] 用英文片名到传统系统搜索验证...")
            verified_items = await self._verify_with_kb(llm_items)

            if verified_items:
                logger.info(
                    f"   [验证结果] {len(verified_items)}/{len(llm_items)} 部电影在数据库中找到"
                )
                llm_result["data"]["items"] = verified_items
                llm_result["data"]["source"] = "llm_kb_verified"

                if len(verified_items) < len(llm_items):
                    missing_count = len(llm_items) - len(verified_items)
                    logger.info(f"   [验证结果] {missing_count} 部电影未在数据库中找到，已跳过")
            else:
                logger.warning("   [验证结果] 所有电影均未在数据库中找到，使用传统推荐降级...")
                result = await self._get_traditional_recommendation(state, extracted_info)
                state["agent_results"].append(result)
                return state

            state["agent_results"].append(llm_result)
            return state

        except Exception as e:
            logger.error(f"   [异常] RecommendAgent 执行异常: {str(e)}")
            intent_analysis = state.get("intent_analysis", {})
            extracted_info = intent_analysis.get("extracted_info", {})
            result = await self._get_traditional_recommendation(state, extracted_info)
            state["agent_results"].append(result)
            return state

    async def _get_traditional_recommendation(
        self, state: MultiAgentState, extracted_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用传统推荐系统（降级方案）

        调用 backend 的推荐 API 获取真实存在的电影
        """
        try:
            from services.integration.trad_rec_client import trad_rec_client

            user_id = state.get("user_id", "")
            genre = extracted_info.get("genre", "")

            # 调用传统推荐系统
            candidates = await trad_rec_client.get_recommendations(
                user_id=user_id, top_k=5, preferred_genres=[genre] if genre else None
            )

            if candidates:
                logger.info(f"   [传统推荐] 返回 {len(candidates)} 部电影")
                # 将 RecommendationItem 对象转换为字典
                items = []
                for item in candidates:
                    items.append(
                        {
                            "movie_id": item.movie_id,
                            "title": item.title,
                            "genres": item.genres,
                            "score": item.score,
                            "poster_url": item.poster_url or "",
                            "reason": item.reason or "",
                        }
                    )

                return {
                    "agent_name": self.name,
                    "success": True,
                    "data": {"items": items, "source": "traditional_fallback"},
                    "error": None,
                }
            else:
                logger.warning("   [传统推荐] 未返回结果")
                return {
                    "agent_name": self.name,
                    "success": False,
                    "data": {"items": [], "source": "traditional_empty"},
                    "error": "传统推荐系统未返回结果",
                }

        except Exception as e:
            logger.error(f"   [传统推荐] 调用失败: {str(e)}")
            return {
                "agent_name": self.name,
                "success": False,
                "data": None,
                "error": f"传统推荐调用失败: {str(e)}",
            }

    async def _generate_with_llm(
        self, state: MultiAgentState, extracted_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        LLM 生成推荐（自由生成）
        """
        if not self.llm_router or not self.llm_router._initialized:
            return {
                "agent_name": self.name,
                "success": False,
                "data": None,
                "error": "LLM 未初始化，无法生成推荐",
            }

        context_parts = []
        if extracted_info.get("genre"):
            context_parts.append(f"- 类型偏好：{extracted_info['genre']}")
        if extracted_info.get("mood"):
            context_parts.append(f"- 心情/场景：{extracted_info['mood']}")
        if extracted_info.get("year"):
            context_parts.append(f"- 年份/年代：{extracted_info['year']}")
        if extracted_info.get("other"):
            context_parts.append(f"- 其他需求：{extracted_info['other']}")

        context_str = "\n".join(context_parts) if context_parts else "- 无特定偏好"

        # 获取已推荐的电影列表（防止重复推荐）
        memory_context = state.get("memory_context", "")
        already_recommended = self._extract_recommended_movies(memory_context)

        system_prompt = """你是一个专业的电影推荐助手，名叫"小影"。请根据用户的需求推荐电影。

重要规则：
1. 请只推荐真实存在的知名电影，不要虚构电影名称
2. 每部电影必须同时提供中文名(title_zh)和英文名(title_en)
3. 英文名必须是 IMDb 数据库中常见的官方英文名（用于搜索匹配）
4. 绝对不要推荐【已推荐列表】中的电影，推荐全新的电影

请以 JSON 格式返回推荐结果，包含以下字段：

{
    "items": [
        {
            "title_zh": "中文电影名",
            "title_en": "English movie title",
            "genres": ["类型"],
            "score": 8.5,
            "reason": "推荐理由"
        }
    ],
    "source": "llm"
}

要求：
1. 推荐 3-5 部电影
2. 每部电影都要有简短的推荐理由
3. 评分使用 1-10 之间的数字
4. 类型使用中文，如 ["科幻", "动作", "冒险"]
5. title_en 必须使用 IMDb 官方英文名，例如：
   - "肖申克的救赎" → "The Shawshank Redemption"
   - "千与千寻" → "Spirited Away"
   - "寄生虫" → "Parasite"
   - "盗梦空间" → "Inception"
   - "阿甘正传" → "Forrest Gump"
6. title_zh 用于最终展示给用户，title_en 用于搜索匹配数据库
7. 不要虚构不存在的电影

注意：只返回 JSON，不要其他内容。"""

        user_prompt = f"用户需求：{state['user_input']}\n\n"
        user_prompt += f"提取的偏好信息：\n{context_str}\n\n"

        if already_recommended:
            user_prompt += "【已推荐列表】（绝对不要重复推荐这些电影）：\n"
            user_prompt += ", ".join(already_recommended)
            user_prompt += "\n\n"

        user_prompt += "请根据以上需求推荐适合的电影。"

        from langchain_core.messages import HumanMessage, SystemMessage

        try:
            response = await self.llm_router.call_llm(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
            )

            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]

            result_data = json.loads(content)

            items = result_data.get("items", [])

            logger.info(f"   [LLM] LLM 生成了 {len(items)} 部推荐电影")

            return {"agent_name": self.name, "success": True, "data": result_data, "error": None}

        except Exception as e:
            logger.error(f"   [LLM生成失败] {str(e)}")
            return {
                "agent_name": self.name,
                "success": False,
                "data": None,
                "error": f"LLM 生成失败: {str(e)}",
            }

    async def _verify_with_kb(self, llm_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        用英文片名到传统系统搜索验证电影是否存在

        流程：
        1. 用 LLM 提供的英文片名(title_en)调用传统系统的精确搜索 API
        2. 搜索使用 match_phrase 精确短语匹配，结果可信
        3. 找到的：使用数据库真实数据（movie_id, poster_url, 评分等），中文名用 LLM 的 title_zh
        4. 没找到的：保留 LLM 原始数据，附加 IMDB 搜索链接

        Args:
            llm_items: LLM 生成的推荐列表（包含 title_zh 和 title_en）

        Returns:
            验证通过的电影列表
        """
        verified = []

        for item in llm_items:
            title_en = item.get("title_en", "").strip()
            title_zh = item.get("title_zh", item.get("title", "")).strip()

            if not title_en:
                logger.info("   [验证] 跳过空英文标题")
                continue

            # 用英文片名搜索 Elasticsearch（ES 中存的是英文片名）
            movie_info = await trad_rec_client.search_movie_by_title(title_en)

            if movie_info:
                found_title_en = movie_info.get("title", title_en)
                movie_id = movie_info.get("movie_id", 0)

                # genres 已经是列表格式
                genres_list = movie_info.get("genres", [])
                if isinstance(genres_list, str):
                    genres_list = [g.strip() for g in genres_list.split("/") if g.strip()]

                verified_item = {
                    "movie_id": movie_id,
                    "title": title_zh,  # 用中文标题展示
                    "title_en": found_title_en,
                    "genres": genres_list,
                    "score": movie_info.get("imdb_rating", item.get("score", 0)),
                    "year": movie_info.get("year", item.get("year", "")),
                    "poster_url": f"/images/{movie_id}.png",
                    "reason": item.get("reason", ""),
                    "source": "database",
                }
                verified.append(verified_item)
                logger.info(
                    f"   [验证✓] '{title_zh}' ({title_en}) -> '{found_title_en}' ID:{movie_id}"
                )
            else:
                # 数据库中没有，保留 LLM 原始数据并附加 IMDB 链接
                imdb_search_url = f"https://www.imdb.com/find/?q={title_en.replace(' ', '+')}"
                verified_item = {
                    "movie_id": 0,
                    "title": title_zh,
                    "title_en": title_en,
                    "genres": item.get("genres", []),
                    "score": item.get("score", 0),
                    "poster_url": "",
                    "reason": item.get("reason", ""),
                    "imdb_url": imdb_search_url,
                    "source": "llm_only",
                }
                verified.append(verified_item)
                logger.info(f"   [验证⚠] '{title_zh}' ({title_en}) 数据库未找到，使用 IMDB 链接")

        return verified

    def _extract_recommended_movies(self, memory_context: str) -> List[str]:
        """
        从记忆上下文中提取已推荐的电影名

        Args:
            memory_context: 记忆上下文字符串

        Returns:
            已推荐的电影名列表
        """
        if not memory_context:
            return []

        movies = []
        for line in memory_context.split("\n"):
            line = line.strip()
            # 匹配 "【电影名列表】（用于代词解析）" 后面的内容
            if "电影名列表" in line or "上次推荐的电影" in line:
                continue
            # 匹配电影行：以 "- " 开头，或者包含在电影列表中
            if line.startswith("- ") and (
                "上映" in line or "年" in line or "评分" in line or "(" in line
            ):
                # 提取电影名（在 "- " 和 " (" 之间）
                movie_part = line[2:].strip()
                title = movie_part.split(" (")[0].split("（")[0].strip()
                if title:
                    movies.append(title)
            # 匹配逗号分隔的电影名列表行
            elif "，" in line or "," in line:
                # 可能是电影名列表
                parts = line.replace("，", ",").split(",")
                for part in parts:
                    part = part.strip()
                    if (
                        part
                        and len(part) > 1
                        and not part.startswith("【")
                        and not part.startswith("-")
                    ):
                        movies.append(part)

        return list(set(movies))  # 去重
