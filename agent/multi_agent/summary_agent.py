"""
总结Agent - 输出整理专家

负责整合各Agent的结果，生成最终的自然语言回复
"""

import re

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from agent.multi_agent import BaseAgent, MultiAgentState

logger = structlog.get_logger()


def _safe_log(text: str) -> str:
    """清理 emoji 字符，避免 Windows GBK 编码错误"""
    # 移除所有 emoji 字符（Unicode 范围）
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "\U0001f900-\U0001f9ff"  # supplemental symbols
        "\U0001fa00-\U0001fa6f"  # chess symbols
        "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text)


class SummaryAgent(BaseAgent):
    """
    总结Agent - 输出整理专家

    职责：
    - 收集各Agent的执行结果
    - 整合信息
    - 生成自然、友好的最终回复
    """

    name: str = "summary_agent"
    description: str = "输出整理专家 - 整合各Agent结果，生成最终回复"

    def __init__(self, llm_router=None):
        super().__init__(llm_router)

    async def initialize(self):
        """初始化总结Agent"""
        self._initialized = True
        logger.info("总结Agent初始化完成")

    async def execute(self, state: MultiAgentState) -> MultiAgentState:
        """执行总结任务"""
        try:
            logger.info("[SummaryAgent] 开始执行")
            logger.info("   收集各Agent结果...")
            logger.info(f"   共有 {len(state.get('agent_results', []))} 个Agent执行结果")

            # 构建各Agent结果的上下文
            context = self._build_context(state)
            logger.info(f"   [上下文] 构建完成，长度: {len(context)}")

            if self.llm_router and self.llm_router._initialized:
                # 使用LLM生成自然回复
                logger.info("   [LLM] 调用LLM生成回复...")
                final_response = await self._generate_with_llm(state, context)
                safe_preview = _safe_log(final_response[:100])
                logger.info(f"   [成功] LLM生成成功，回复长度: {len(final_response)}")
                logger.info(f"   [预览] {safe_preview}...")
            else:
                # 降级方案：使用模板生成
                logger.info("   [降级] LLM未初始化，使用降级方案")
                final_response = self._generate_fallback(state, context)
                safe_preview = _safe_log(final_response[:100])
                logger.info(f"   [成功] 降级方案生成成功，回复长度: {len(final_response)}")
                logger.info(f"   [预览] {safe_preview}...")

            state["final_response"] = final_response

            return state

        except Exception as e:
            logger.error(f"   [异常] SummaryAgent 执行异常: {str(e)}")
            state["final_response"] = "抱歉，系统处理时出现了一些问题。"
            state["error"] = str(e)
            return state

    def _build_context(self, state: MultiAgentState) -> str:
        """构建各Agent结果的上下文"""
        context_parts = []

        for result in state.get("agent_results", []):
            agent_name = result.get("agent_name", "unknown")
            success = result.get("success", False)
            data = result.get("data")

            if success and data:
                if agent_name == "recommend_agent":
                    items = data.get("items", [])
                    if items:
                        movies_info = "\n".join(
                            [
                                f"- {m.get('title', '未知')} ({m.get('genres', '')}) 评分: {m.get('rating', 'N/A')} 年份: {m.get('year', '未知')}"
                                for m in items[:5]
                            ]
                        )
                        context_parts.append(f"推荐结果:\n{movies_info}")

                elif agent_name == "search_agent":
                    source = data.get("source", "unknown")
                    if source == "knowledge_base":
                        movies = data.get("movies", [])
                        if movies:
                            search_info = "\n".join(
                                [
                                    f"- {m.get('title', '未知')}: 导演 {m.get('director', '未知')}, {m.get('year', '')}年, {m.get('genres', '')}"
                                    for m in movies[:3]
                                ]
                            )
                            context_parts.append(f"知识库搜索结果:\n{search_info}")
                    else:
                        context_parts.append(f"搜索引擎结果: {data.get('response', '')}")
            else:
                context_parts.append(f"{agent_name}: 执行失败 - {result.get('error', '未知错误')}")

        return "\n\n".join(context_parts)

    async def _generate_with_llm(self, state: MultiAgentState, context: str) -> str:
        """使用LLM生成回复"""
        # 获取意图分析结果
        intent_analysis = state.get("intent_analysis", {})
        intent_type = intent_analysis.get("intent_type", "unknown")
        extracted_info = intent_analysis.get("extracted_info", {})

        # 获取对话历史
        conversation_history = self._format_conversation_history(state)

        # 获取记忆内存上下文
        memory_context = state.get("memory_context", "")

        system_prompt = """你是一个专业的电影推荐助手，名叫"小影"。你是一个热爱电影的温暖朋友，不是冷冰冰的机器。

【你的身份】
你是一个电影狂热爱好者，喜欢和人聊天。你有自己的品味和想法，不是机械地回答问题的工具。你说话像朋友一样自然、温暖、有温度。

【你的核心能力】
1. 根据用户需求推荐合适的电影
2. 回答关于电影的详细信息（导演、演员、剧情、评分等）
3. 和用户聊电影相关话题
4. 根据用户的心情和场景给出贴心建议

【回复格式指导】

**推荐场景**（当用户要求推荐电影时）：
- 开头：亲切地回应用户的需求，表达理解
- 正文：对每部推荐电影，提供：
  * 电影名（用书名号《》）
  * 一句话推荐理由（为什么适合用户）
  * 关键信息：类型、评分、年份
  * 简短剧情介绍（1-2句话）
- 结尾：询问用户对哪部感兴趣，或者想要其他类型的推荐

**搜索场景**（当用户查询电影信息时）：
- 开头：确认用户想了解的电影
- 正文：整合搜索到的信息，用清晰的格式展示
- 结尾：询问是否需要更多帮助

**闲聊场景**（打招呼、问你是谁、感谢、情感交流等）：
- 像朋友一样自然聊天，不要机械化
- 如果是"你是谁"，简单介绍自己是小影，帮他们发现好电影的伙伴
- 如果是打招呼，热情回应并引导话题
- 如果是感谢，轻松回应并表示随时帮忙
- 如果用户表达情感，给予温暖的回应
- 自然地引导用户表达观影需求，但不要显得太功利

【多轮对话上下文感知】（非常重要）
- 如果用户使用了代词（如"这些电影"、"它们"、"哪部"等），必须从上下文中找到具体指代的内容
- 如果当前输入没有明确提到具体电影名，但用户的问题显然是针对上一次推荐的电影，请仔细阅读对话历史中的推荐列表
- 回答关于电影的问题时，优先使用上下文中的电影信息，而不是编造新内容
- 如果用户在追问上一轮推荐电影的属性（如国家、导演、类型等），请基于上一次推荐的电影来回答，不要随意更换电影

【语气和风格】
1. 像朋友聊天，不要太正式或机械
2. 适当使用表情符号增加亲和力（但不要过度）
3. 真诚、有温度，让用户感受到你是真心在帮他们
4. 避免重复使用相同的句式
5. 展现你对电影的了解和热情
6. 使用中文，口语化但不失专业

【绝对禁止的行为】
- 不要说"根据搜索结果"或"根据推荐结果"这类机械话
- 不要罗列数据，要有叙述感
- 不要说"作为一个AI"或"作为一个人工智能助手"之类的话
- 不要说"我很乐意"、"我很高兴"等机器人常用语
- 不要一次推荐超过5部电影
- 回复不要太长，保持简洁（闲聊2-3句话，推荐4-6句话）

【关于输出格式的严格要求】
- 只输出最终结果，不要展示你的思考过程
- 绝对不要输出"等等不对！"、"让我想想"、"正确答案是"这类思考过程
- 绝对不要输出任何思考标签（如 <originalContent>、<thought>、<reasoning> 等）
- 不要展示自我纠错过程（如"刚才推荐的不符合，现在重新推荐"）
- 不要展示你筛选或排除电影的过程
- 如果某部电影不符合要求，直接跳过它，不要提它
- 直接给出符合要求的最终推荐，不要解释为什么排除其他电影
- 如果推荐结果中有不符合用户需求的电影，直接忽略它们，只推荐符合的

记住：你是在和朋友聊天，不是在执行任务。让每次对话都自然、温暖、有人情味！"""

        # 构建用户消息，包含意图分析和对话历史
        user_message_parts = []

        # 添加记忆内存上下文
        if memory_context:
            user_message_parts.append(f"【记忆上下文】\n{memory_context}")

        # 添加意图分析信息
        if intent_type != "unknown":
            user_message_parts.append(f"【当前意图】{intent_type}")
            if extracted_info:
                info_parts = [f"{k}: {v}" for k, v in extracted_info.items() if v]
                if info_parts:
                    user_message_parts.append(f"【提取信息】{', '.join(info_parts)}")

        user_message_parts.append(f"【用户当前输入】{state['user_input']}")

        # 添加对话历史
        if conversation_history:
            user_message_parts.append(f"【最近对话历史】\n{conversation_history}")

        # 添加Agent执行结果
        if context:
            user_message_parts.append(f"【执行结果】\n{context}")

        user_message_parts.append("\n请根据以上信息，生成一个自然、专业的回复。")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="\n\n".join(user_message_parts)),
        ]

        response = await self.llm_router.call_llm(messages)

        return response.content

    def _format_conversation_history(self, state: MultiAgentState) -> str:
        """格式化对话历史"""
        messages = state.get("messages", [])
        if not messages:
            return ""

        # 只显示最近3轮对话
        recent_messages = messages[-6:] if len(messages) > 6 else messages

        history_lines = []
        for msg in recent_messages:
            if hasattr(msg, "type"):
                if msg.type == "human":
                    history_lines.append(f"用户: {msg.content}")
                elif msg.type == "ai":
                    history_lines.append(f"小影: {msg.content}")

        return "\n".join(history_lines) if history_lines else ""

    def _generate_fallback(self, state: MultiAgentState, context: str) -> str:
        """降级方案：使用模板生成回复"""
        results = state.get("agent_results", [])

        # 查找推荐结果
        recommend_result = None
        for r in results:
            if r.get("agent_name") == "recommend_agent" and r.get("success"):
                recommend_result = r
                break

        if recommend_result:
            data = recommend_result.get("data", {})
            items = data.get("items", [])

            if items:
                movies_list = "\n".join(
                    [
                        f"{i}. {m.get('title', '未知')} ({m.get('genres', '')}) - 评分: {m.get('rating', 'N/A')}"
                        for i, m in enumerate(items[:5], 1)
                    ]
                )

                return f"根据你的需求，我为你推荐以下电影：\n\n{movies_list}\n\n希望你喜欢！如果想了解某部电影的详细信息，随时告诉我~"

        # 没有推荐结果，检查是否是闲聊
        user_input = state.get("user_input", "").lower()

        # 闲聊场景
        if any(kw in user_input for kw in ["你是谁", "叫什么", "介绍自己", "你好", "嗨", "hello"]):
            return "你好！我是小影，你的电影推荐助手。我可以帮你发现好看的电影，推荐适合你心情的影片，或者回答关于电影的问题。告诉我你想看什么类型的电影吧！"

        # 感谢场景
        if any(kw in user_input for kw in ["谢谢", "感谢", "thanks"]):
            return "不客气！如果还需要推荐其他电影，随时告诉我~"

        # 默认回复
        return "抱歉，我暂时没有为你找到合适的推荐。你可以告诉我你喜欢的电影类型或者心情，我会更好地为你推荐~"
