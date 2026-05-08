"""
多Agent协调器

管理多Agent的协作流程，支持流式输出
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from agent.multi_agent import MultiAgentState
from agent.multi_agent.master_agent import MasterAgent
from llm.llm_router import LLMRouter
from services.dialogue.dialogue_history import dialogue_history
from services.memory.memory_bank import memory_bank
from services.queue.task_queue import task_queue

logger = structlog.get_logger()


@dataclass
class ThinkingStep:
    """思考步骤"""

    type: str
    content: str
    agent_name: str = ""
    timestamp: float = 0.0


class MultiAgentCoordinator:
    """
    多Agent协调器

    管理主Agent和各专业Agent的协作流程
    支持流式输出：通过 callback 实时推送 thinking 事件
    使用记忆内存（MemoryBank）维护多轮对话上下文
    """

    def __init__(self):
        self.llm_router = None
        self.master_agent = None
        self._initialized = False
        self._thinking_queue = []
        self._stream_callback: Optional[Callable] = None

    async def initialize(self):
        """初始化所有Agent"""
        if self._initialized:
            return

        self.llm_router = LLMRouter()
        await self.llm_router.initialize()

        self.master_agent = MasterAgent(self.llm_router)
        await self.master_agent.initialize()

        await dialogue_history.initialize()
        await memory_bank.initialize()

        self._initialized = True
        logger.info("多Agent协调器初始化完成")

    def _add_thinking_step(self, step_type: str, content: str, agent_name: str = ""):
        """添加思考步骤，如果设置了流式回调则立即推送"""
        step = ThinkingStep(
            type=step_type, content=content, agent_name=agent_name, timestamp=time.time()
        )
        self._thinking_queue.append(step)

        if self._stream_callback:
            self._stream_callback(step)

    async def process_request(
        self,
        user_input: str,
        user_id: str = "anonymous",
        stream_callback: Optional[Callable[[ThinkingStep], None]] = None,
    ) -> Dict[str, Any]:
        """
        处理用户请求

        Args:
            user_input: 用户输入
            user_id: 用户ID
            stream_callback: 流式回调，每个 thinking step 都会调用

        Returns:
            处理结果
        """
        start_time = time.time()

        self._thinking_queue = []
        self._stream_callback = stream_callback

        if not self._initialized:
            self._add_thinking_step("initializing", "[初始化] 初始化多Agent协调器...")
            await self.initialize()

        # Q&A 场景不使用缓存，每次根据当前上下文重新生成
        self._add_thinking_step("start", "[开始] 处理请求...")

        conversation_history = dialogue_history.get_history(user_id, n=5)

        messages = []
        for turn in conversation_history:
            messages.append(HumanMessage(content=turn.user_input))
            messages.append(AIMessage(content=turn.agent_response))

        # 从记忆内存加载上下文
        self._add_thinking_step("memory", "[记忆] 加载用户记忆...")
        memory_context = await memory_bank.get_context_summary(user_id)
        if memory_context:
            self._add_thinking_step(
                "memory_loaded", f"[记忆] 已加载记忆上下文，长度: {len(memory_context)}"
            )

        state = MultiAgentState(
            user_input=user_input,
            user_id=user_id,
            task_plan=[],
            agent_results=[],
            final_response="",
            messages=messages,
            current_step=0,
            error=None,
            intent_analysis={},
            react_logs=[],
            react_iterations=0,
            react_max_iterations_reached=False,
            memory_context=memory_context,
        )

        try:
            state = await self.master_agent.execute(state)

            elapsed = time.time() - start_time

            self._add_thinking_step("done", "[完成] 处理完成")

            result = {
                "response": state.get("final_response", ""),
                "latency_ms": round(elapsed * 1000, 2),
                "task_plan": state.get("task_plan", []),
                "agent_results": state.get("agent_results", []),
                "error": state.get("error"),
                "thinking_steps": self.get_thinking_steps(),
            }

            # 异步保存推荐结果到记忆内存（不阻塞主流程）
            for agent_result in state.get("agent_results", []):
                if agent_result.get("agent_name") == "recommend_agent" and agent_result.get(
                    "success"
                ):
                    data = agent_result.get("data", {})
                    items = data.get("items", [])
                    if items:
                        await task_queue.enqueue(
                            "save_recommendation",
                            {"user_id": user_id, "movies": items, "query": user_input, "ttl": 1800},
                        )
                        self._add_thinking_step(
                            "memory_save", f"[记忆] 已入队保存 {len(items)} 部推荐电影"
                        )

            # 异步保存对话历史（不阻塞主流程）
            await task_queue.enqueue(
                "save_dialogue",
                {
                    "user_id": user_id,
                    "user_input": user_input,
                    "agent_response": result["response"],
                    "intent": state.get("intent_analysis", {}).get("intent_type", "multi_agent"),
                    "skill_used": "multi_agent",
                },
            )

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("[错误] 多Agent处理失败", error=str(e))
            self._add_thinking_step("error", f"[错误] 处理失败: {str(e)}")

            return {
                "response": self._friendly_error_message(str(e)),
                "latency_ms": round(elapsed * 1000, 2),
                "error": str(e),
                "thinking_steps": self.get_thinking_steps(),
            }

    def _friendly_error_message(self, error: str) -> str:
        """根据错误类型返回友好的错误提示"""
        error_lower = error.lower()

        if any(kw in error_lower for kw in ["connection", "connect", "refused", "timeout"]):
            return "抱歉，推荐引擎暂时无法连接，请稍后再试。"

        if "openai" in error_lower or "llm" in error_lower or "model" in error_lower:
            return "抱歉，我的大脑正在思考中，请稍后再试。"

        if "redis" in error_lower:
            return "抱歉，缓存系统暂时不可用，但推荐功能仍然正常。"

        return "抱歉，系统处理时出现了一些问题，请稍后再试。"

    def get_thinking_steps(self, clear: bool = True) -> list:
        """获取思考步骤"""
        steps = [
            {
                "type": step.type,
                "content": step.content,
                "agent_name": step.agent_name,
                "timestamp": step.timestamp,
            }
            for step in self._thinking_queue
        ]
        if clear:
            self._thinking_queue.clear()
        return steps


multi_agent_coordinator = MultiAgentCoordinator()
