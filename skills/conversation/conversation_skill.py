"""
对话技能

处理用户的闲聊、情感回应、追问等对话交互
"""

from typing import Any, Dict

import structlog

from skills.base import BaseSkill

logger = structlog.get_logger()


class ConversationSkill(BaseSkill):
    """
    对话技能

    处理闲聊、情感回应、知识问答、追问等对话场景
    """

    name: str = "conversation_skill"
    description: str = "处理对话交互，包括闲聊和情感回应"
    priority: int = 1  # 最高优先级，处理非任务对话

    # 意图分类模式
    intent_patterns = {
        "greeting": ["你好", "嗨", "在吗", "早上好", "晚上好"],
        "emotion": ["开心", "难过", "心情", "无聊", "累"],
        "follow_up": ["还有吗", "换一个", "类似的", "继续"],
        "thanks": ["谢谢", "感谢", "太好了"],
    }

    async def _execute(
        self, user_input: str, user_id: str = None, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        执行对话技能

        Args:
            user_input: 用户输入
            user_id: 用户 ID
            context: 上下文信息

        Returns:
            对话响应
        """
        logger.info("执行对话技能", user_input=user_input[:50])

        # 1. 意图分类
        intent = self._classify_intent(user_input)

        # 2. 使用 LLM 生成智能响应
        response = await self._generate_smart_response(user_input, intent, context)

        return {"success": True, "response": response, "intent": intent, "skill": self.name}

    def _classify_intent(self, user_input: str) -> str:
        """
        意图分类

        Args:
            user_input: 用户输入

        Returns:
            意图类型
        """
        user_input_lower = user_input.lower()

        for intent, patterns in self.intent_patterns.items():
            for pattern in patterns:
                if pattern in user_input_lower:
                    return intent

        return "unknown"

    async def _generate_smart_response(
        self, user_input: str, intent: str, context: Dict[str, Any] = None
    ) -> str:
        """使用 LLM 生成智能对话响应"""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from llm.llm_router import LLMRouter

            llm_router = LLMRouter()
            await llm_router.initialize()
            llm = llm_router.get_llm()

            system_prompt = """你是一个电影推荐助手，但不要用机器人或助手的语气说话。像一个真正的朋友一样与用户交流。

核心原则：
1. 理解用户话语背后的真实意图和情感
2. 用自然、温暖、有人情味的方式回应
3. 像朋友聊天一样，不要使用"作为AI助手"、"我很乐意"等机械化表达
4. 主动但不过度，给用户选择的空间
5. 回复要简洁，通常2-3句话就够了

回复风格参考：
- ❌ "作为AI助手，我很乐意为你推荐电影"
- ✅ "嗨！今天想看什么类型的电影？我帮你推荐几部~"
- ❌ "我理解你的感受，让我为你推荐..."
- ✅ "心情不好的时候看部电影确实能放松一下，你喜欢什么类型的？"

当用户问"你是谁"时：
- 简单介绍自己是帮他们发现好电影的伙伴
- 轻松幽默地回应
- 引导他们表达观影需求

记住：你是在和朋友聊天，不是在完成任务！"""

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"用户说：{user_input}"),
            ]

            response = await llm.ainvoke(messages)
            return response.content

        except Exception as e:
            logger.warning(f"LLM 生成失败，使用默认响应: {e}")
            return self._get_fallback_response(user_input, intent)

    def _get_fallback_response(self, user_input: str, intent: str) -> str:
        """LLM 失败时的降级响应"""
        fallbacks = {
            "greeting": "你好呀！我是你的电影推荐小助手 🎬 今天想看什么类型的电影呢？",
            "emotion": "我理解你的心情~ 要不要看部电影放松一下？告诉我你喜欢什么类型的电影吧！",
            "follow_up": "当然可以！你还想了解哪方面的电影推荐呢？",
            "thanks": "不客气！ 😊 如果还需要其他推荐，随时告诉我哦~",
            "unknown": "我明白你的意思~ 我是电影推荐助手，有什么想看的电影可以告诉我哦！比如喜欢的类型或者心情~",
        }
        return fallbacks.get(intent, fallbacks["unknown"])
