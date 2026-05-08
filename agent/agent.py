"""
智能电影推荐 Agent 核心

基于 LangGraph + bind_tools 的真正 Agent
LLM 自主决策调用哪个工具，支持所有 LLM
"""

import time
import json
import re
import os
from pathlib import Path
from typing import Dict, Any, TypedDict, Annotated, Optional, Sequence, List, Literal

from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from agent.config.agent_config import config
from llm.llm_router import LLMRouter
from skills.conversation.conversation_skill import ConversationSkill
from skills.recommend.recommend_skill import RecommendSkill
from skills.search.search_skill import SearchSkill
from skills.profile.profile_skill import ProfileSkill
from skills.scene.scene_skill import SceneSkill
from services.cache.redis_cache import redis_cache
from services.dialogue.dialogue_history import dialogue_history
from services.recommendation.engine_adapter import recommendation_engine

logger = structlog.get_logger()


# Agent 状态定义
class AgentState(TypedDict):
    """Agent 状态"""
    messages: Sequence[BaseMessage]
    user_input: str
    user_id: str
    response: str
    latency_ms: float
    steps: int


class MovieRecommendAgent:
    """
    智能电影推荐 Agent
    
    使用 bind_tools 模式，LLM 自主决定使用哪个工具
    """
    
    def __init__(self):
        self.config = config
        self.llm_router = LLMRouter()
        
        # 初始化 Skills
        self.conversation_skill = ConversationSkill()
        self.recommend_skill = RecommendSkill()
        self.search_skill = SearchSkill()
        self.profile_skill = ProfileSkill()
        self.scene_skill = SceneSkill()
        
        # 对话历史存储
        self._conversation_memory: Dict[str, List[Dict]] = {}
        
        # 工具列表
        self._tools = []
        
        self._initialized = False
    
    async def initialize(self):
        """初始化 Agent"""
        if self._initialized:
            return
        
        await redis_cache.connect()
        await self.llm_router.initialize()
        await recommendation_engine.initialize()
        
        # 创建工具
        self._create_tools()
        
        self._initialized = True
        logger.info("Agent 初始化完成")
    
    def _create_tools(self):
        """创建工具列表"""
        
        @tool
        def recommend_movies(query: str) -> str:
            """推荐电影的主要工具。适用于以下场景：
            1. 用户要求推荐电影（"推荐电影"、"有什么好看的"）
            2. 用户表达心情/情绪（"心情不好"、"无聊"、"开心"、"难过"）
            3. 用户提到电影类型（"科幻片"、"喜剧"、"悬疑"）
            4. 用户说想看电影、求推荐等
            当用户有任何看电影的意图时，都应该调用此工具。
            参数query应该是用户的原始输入或心情描述。"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.recommend_skill.execute(
                        user_id="anonymous",
                        context={"query": query},
                        top_k=self.config.recommendation.final_top_k
                    )
                )
                if result.get("success"):
                    data = result.get("data", {})
                    items = data.get("items", [])
                    if items:
                        movies_str = "\n".join([f"- {m.get('title', '未知')} ({m.get('genres', '')}) 评分: {m.get('rating', 'N/A')}" for m in items[:5]])
                        return f"根据你的情况推荐以下电影：\n{movies_str}"
                    return "推荐成功，但没有找到匹配的电影"
                return f"推荐失败: {result.get('error', '未知错误')}"
            finally:
                loop.close()
        
        @tool
        def search_movie(query: str) -> str:
            """搜索特定电影。当用户提到具体电影名称时使用。
            示例：搜索复仇者联盟、有没有星际穿越"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.search_skill.execute(query=query, user_id="anonymous", top_k=5)
                )
                return result.get("response", "未找到")
            finally:
                loop.close()
        
        @tool
        def chat_conversation(query: str) -> str:
            """与用户进行闲聊对话。当用户打招呼、表达情感、问你是谁、谢谢时使用。
            示例：你好、谢谢、你是谁"""
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.conversation_skill.execute(user_input=query, user_id="anonymous")
                )
                return result.get("response", "")
            finally:
                loop.close()
        
        self._tools = [recommend_movies, search_movie, chat_conversation]
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是电影推荐助手"小影"，一个热爱电影的贴心朋友。

你的能力：
- 推荐各种类型的电影
- 回答关于电影的知识问题
- 根据用户心情推荐合适的电影

回复风格：
- 语气自然亲切，像朋友聊天
- 使用表情符号增加亲和力
- 简洁明了，2-3句话为主

重要规则：
1. 当用户表达情绪或心情（如"心情不好"、"无聊"、"开心"）时，主动推荐电影！
2. 当用户要求推荐电影时，使用 recommend_movies 工具
3. 当用户搜索特定电影时，使用 search_movie 工具
4. 日常闲聊使用 chat_conversation 工具
5. 使用工具获取真实信息，不要编造电影名或信息！

特别注意：如果用户说"心情不好"、"无聊"、"想看电影"等，一定要调用 recommend_movies 工具！"""
    
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 状态图"""
        workflow = StateGraph(AgentState)
        
        # 使用预构建的 ToolNode
        tool_node = ToolNode(self._tools)
        
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", tool_node)
        
        workflow.set_entry_point("agent")
        
        workflow.add_conditional_edges(
            "agent",
            self._should_use_tools,
            {
                "tools": "tools",
                "__end__": END,
            }
        )
        
        workflow.add_edge("tools", "agent")
        
        return workflow.compile()
    
    async def _agent_node(self, state: AgentState) -> Dict:
        """Agent 节点 - 使用 bind_tools"""
        llm = self.llm_router.get_llm()
        
        # 绑定工具到 LLM
        llm_with_tools = llm.bind_tools(self._tools)
        
        # 获取对话上下文
        context = self._get_conversation_context(state["user_id"])
        
        # 构建消息
        system_prompt = self._get_system_prompt()
        messages = [SystemMessage(content=f"{system_prompt}\n\n{context}")]
        
        # 添加历史消息（如果有的话）
        existing_messages = state.get("messages", [])
        if existing_messages:
            messages.extend(existing_messages)
        
        # 如果没有历史消息，添加当前用户输入
        if not existing_messages:
            messages.append(HumanMessage(content=state["user_input"]))
        
        # 调用 LLM
        response = await llm_with_tools.ainvoke(messages)
        
        # 检查是否有工具调用
        if hasattr(response, 'tool_calls') and response.tool_calls:
            # LLM 决定调用工具
            return {
                "messages": existing_messages + [response],
                "user_input": state["user_input"],
                "steps": state.get("steps", 0) + 1,
            }
        else:
            # LLM 直接回复
            return {
                "messages": existing_messages + [response],
                "response": response.content,
                "user_input": state["user_input"],
                "steps": state.get("steps", 0) + 1,
            }
    
    def _should_use_tools(self, state: AgentState) -> Literal["tools", "__end__"]:
        """判断是否需要调用工具"""
        messages = state.get("messages", [])
        if not messages:
            return "__end__"
        
        # 如果达到最大步骤数，强制结束
        if state.get("steps", 0) >= 3:
            return "__end__"
        
        last_message = messages[-1]
        
        # 检查最后一条消息是否有工具调用
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        
        # 如果有response，说明已经完成
        if state.get("response"):
            return "__end__"
        
        return "__end__"
    
    def _get_conversation_context(self, user_id: str) -> str:
        """获取对话上下文"""
        history = self._conversation_memory.get(user_id, [])
        if not history:
            return ""
        
        context_lines = ["之前的对话："]
        for turn in history[-5:]:
            context_lines.append(f"用户: {turn['user']}")
            context_lines.append(f"助手: {turn['assistant']}")
        
        return "\n".join(context_lines)
    
    def _save_conversation(self, user_id: str, user_msg: str, assistant_msg: str):
        """保存对话到记忆"""
        if user_id not in self._conversation_memory:
            self._conversation_memory[user_id] = []
        
        self._conversation_memory[user_id].append({
            "user": user_msg,
            "assistant": assistant_msg
        })
        
        if len(self._conversation_memory[user_id]) > 10:
            self._conversation_memory[user_id] = self._conversation_memory[user_id][-10:]
    
    async def invoke(
        self,
        user_input: str,
        user_id: str = "anonymous",
        messages: Sequence[BaseMessage] = None
    ) -> Dict[str, Any]:
        """调用 Agent 处理用户请求"""
        start_time = time.time()
        
        if not self._initialized:
            await self.initialize()
        
        initial_state = {
            "messages": messages or [],
            "user_input": user_input,
            "user_id": user_id,
            "response": "",
            "latency_ms": 0.0,
            "steps": 0,
        }
        
        try:
            graph = self._build_graph()
            result = await graph.ainvoke(initial_state)
            
            elapsed = time.time() - start_time
            result["latency_ms"] = round(elapsed * 1000, 2)
            
            # 提取响应
            if not result.get("response"):
                # 如果没有response，尝试从最后一条消息提取
                last_msg = result.get("messages", [])[-1] if result.get("messages") else None
                if last_msg and hasattr(last_msg, 'content'):
                    result["response"] = last_msg.content
                else:
                    result["response"] = "抱歉，我没有理解你的意思。"
            
            # 保存对话
            self._save_conversation(user_id, user_input, result["response"])
            
            # 记录历史
            dialogue_history.add_turn(
                user_id=user_id,
                user_input=user_input,
                agent_response=result.get("response", ""),
                intent="agent_tool",
                skill_used="llm_router"
            )
            
            logger.info(
                "Agent 执行完成",
                user_id=user_id,
                latency_ms=result["latency_ms"],
                steps=result.get("steps", 0)
            )
            
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "Agent 执行失败",
                user_id=user_id,
                error=str(e),
                latency_ms=round(elapsed * 1000, 2)
            )
            
            return {
                "response": "抱歉，系统出现了一些问题。请稍后再试。",
                "latency_ms": round(elapsed * 1000, 2),
                "error": str(e)
            }


# 全局 Agent 实例
agent = MovieRecommendAgent()
