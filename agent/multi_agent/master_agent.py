"""
主Agent - 任务规划专家

负责理解用户需求，分析意图，拆解任务，协调各专业Agent协作
"""

from typing import Dict, Any, List, Optional, Literal
import json
import time
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END

from agent.multi_agent import BaseAgent, MultiAgentState
from agent.multi_agent.recommend_agent import RecommendAgent
from agent.multi_agent.search_agent import SearchAgent
from agent.multi_agent.summary_agent import SummaryAgent
from agent.multi_agent.react_loop import ReActLoop
from llm.llm_router import LLMRouter

import structlog

logger = structlog.get_logger()


class MasterAgent(BaseAgent):
    """
    主Agent - 任务规划专家
    
    职责：
    1. 理解用户需求和意图
    2. 分析需要哪些子任务
    3. 创建任务执行计划
    4. 协调各Agent按顺序执行
    5. 汇总结果并生成最终回复
    """
    
    name: str = "master_agent"
    description: str = "任务规划专家 - 理解用户需求，拆解任务，协调各Agent协作"
    
    def __init__(self, llm_router: LLMRouter = None):
        super().__init__(llm_router)
        self.recommend_agent = RecommendAgent(llm_router)
        self.search_agent = SearchAgent(llm_router)
        self.summary_agent = SummaryAgent(llm_router)
        
        # 子Agent注册
        self._sub_agents = {
            "recommend": self.recommend_agent,
            "search": self.search_agent,
            "summary": self.summary_agent,
        }
    
    async def initialize(self):
        """初始化主Agent及所有子Agent"""
        if self._initialized:
            return
        
        if not self.llm_router:
            self.llm_router = LLMRouter()
            await self.llm_router.initialize()
        
        # 初始化子Agent
        await self.recommend_agent.initialize()
        await self.search_agent.initialize()
        await self.summary_agent.initialize()
        
        self._initialized = True
        logger.info("主Agent初始化完成")
    
    async def execute(self, state: MultiAgentState) -> MultiAgentState:
        """
        执行主Agent任务（增强版 - 带 ReAct 推理循环）
        
        流程：
        1. 分析用户需求，生成任务计划
        2. ReAct 循环执行（最多3次迭代）
           - Thought: 思考当前状态
           - Action: 执行任务
           - Observation: 检查结果质量
           - Reflection: 反思是否需要调整
        3. SummaryAgent 生成最终回复
        """
        try:
            # 步骤1：分析需求，生成初始任务计划
            state = await self._create_task_plan(state)
            
            # 步骤2：ReAct 推理循环执行（只执行 RecommendAgent/SearchAgent）
            # 把 SummaryAgent 从任务计划中分离出来，在循环外执行
            task_plan_without_summary = [
                t for t in state["task_plan"] 
                if t.get("agent") != "summary"
            ]
            
            react_loop = ReActLoop(self.llm_router)
            state = await react_loop.execute_with_reflection(
                state,
                task_plan_without_summary,
                execute_task_fn=self._execute_task,
                execute_task_isolated_fn=self._execute_task_isolated
            )
            
            # 步骤3：ReAct 循环退出后，执行 SummaryAgent 生成最终回复（只执行一次）
            summary_task = {"agent": "summary", "description": "整合结果生成回复"}
            state = await self._execute_task(state, summary_task)
            
            logger.info(
                "多Agent协作完成",
                iterations=state.get("react_iterations", 1),
                results=len(state["agent_results"])
            )
            
            return state
            
        except Exception as e:
            logger.error("主Agent执行失败", error=str(e))
            state["error"] = str(e)
            state["final_response"] = "抱歉，系统处理时出现了一些问题，请稍后再试。"
            return state
    
    async def _create_task_plan(self, state: MultiAgentState) -> MultiAgentState:
        """
        分析用户需求，生成任务执行计划（增强版 - 支持多轮上下文）
        
        使用 LLM 分析意图，结合历史对话理解上下文
        """
        user_input = state['user_input']
        
        # 获取最近的历史对话
        from services.dialogue.dialogue_history import dialogue_history
        recent_history = dialogue_history.get_history(state["user_id"], n=3)
        
        logger.info("=" * 60)
        logger.info("[MasterAgent] 思考过程")
        logger.info("=" * 60)
        logger.info(f"用户需求: {user_input}")
        if recent_history:
            logger.info(f"历史对话: {len(recent_history)} 轮")
        
        # 优先使用 LLM 分析意图（传入历史上下文）
        intent_analysis = await self._analyze_intent_with_llm(
            user_input,
            recent_history
        )
        
        needs_recommend = intent_analysis.get("needs_recommend", False)
        needs_search = intent_analysis.get("needs_search", False)
        intent_type = intent_analysis.get("intent_type", "chat")
        extracted_info = intent_analysis.get("extracted_info", {})
        
        # 多轮上下文增强: 继承历史实体
        if recent_history and len(recent_history) > 0:
            inherited = self._inherit_context_entities(recent_history, extracted_info, intent_type)
            if inherited:
                extracted_info.update(inherited)
                intent_analysis["context_inherited"] = inherited
                logger.info(f"  [上下文继承] 从历史对话中提取: {inherited}")
        
        logger.info("[LLM意图分析]")
        logger.info(f"  - 意图类型: {intent_type}")
        logger.info(f"  - 需要推荐: {needs_recommend}")
        logger.info(f"  - 需要搜索: {needs_search}")
        logger.info(f"  - 提取信息: {extracted_info}")
        
        # 保存意图分析结果到状态，供后续 Agent 使用
        state["intent_analysis"] = intent_analysis
        
        # 生成更精确的任务计划
        task_plan = []
        
        if needs_recommend:
            genre = extracted_info.get("genre", "")
            mood = extracted_info.get("mood", "")
            year = extracted_info.get("year", "")
            
            desc_parts = ["推荐电影"]
            if genre:
                desc_parts.append(f"类型: {genre}")
            if mood:
                desc_parts.append(f"心情/场景: {mood}")
            if year:
                desc_parts.append(f"年份: {year}")
            
            task_plan.append({
                "agent": "recommend", 
                "description": " - ".join(desc_parts),
                "params": extracted_info
            })
            logger.info(f"  [决定] 调用 RecommendAgent - {' - '.join(desc_parts)}")
        
        if needs_search:
            search_target = extracted_info.get("movie_name", user_input)
            task_plan.append({
                "agent": "search", 
                "description": f"搜索电影信息: {search_target}",
                "params": extracted_info
            })
            logger.info(f"  [决定] 调用 SearchAgent - 搜索: {search_target}")
        
        if task_plan:
            logger.info("  [决定] 调用 SummaryAgent - 整合结果生成回复")
            task_plan.append({"agent": "summary", "description": "整合结果生成回复"})
        else:
            logger.info(f"  [决定] 判定为闲聊({intent_type})，只调用 SummaryAgent - 回复用户")
            task_plan.append({"agent": "summary", "description": f"回复用户({intent_type})"})
        
        state["task_plan"] = task_plan
        logger.info(f"[任务计划] {task_plan}")
        logger.info("=" * 60)
        return state
    
    async def _analyze_intent_with_llm(
        self,
        user_input: str,
        conversation_history: list = None
    ) -> Dict[str, Any]:
        """
        使用 LLM 分析用户意图（增强版 - 支持多轮上下文）
        
        Args:
            user_input: 当前用户输入
            conversation_history: 历史对话列表 (可选)
        
        返回结构化意图分析结果
        """
        # 构建上下文信息
        context_info = ""
        if conversation_history and len(conversation_history) > 0:
            context_lines = []
            for turn in conversation_history[-3:]:  # 最近 3 轮
                context_lines.append(f"用户: {turn.user_input}")
                context_lines.append(f"Agent: {turn.agent_response[:100]}")
            context_info = "\n".join(context_lines)
        
        system_prompt = """你是一个意图分析专家，专门分析用户在电影推荐场景下的真实需求。

你支持多轮对话理解，需要：
1. 理解模糊表达（"还有吗"、"这个不错"、"新一点的"）
2. 继承历史上下文中的实体（类型、心情、年份等）
3. 识别指代消解（"这个"指的是上一轮推荐的某部电影）

请以 JSON 格式返回分析结果，包含以下字段：

{
    "intent_type": "意图类型",
    "needs_recommend": true/false,
    "needs_search": true/false,
    "confidence": 0.0-1.0,
    "extracted_info": {
        "genre": "电影类型",
        "mood": "心情或场景",
        "year": "年份或年代",
        "movie_name": "电影名称",
        "other": "其他关键信息"
    },
    "reasoning": "分析理由（简短一句话）"
}

意图类型说明：
- recommend: 用户希望得到电影推荐（包括心情描述、类型偏好、场景描述等间接表达）
- search: 用户询问具体电影的信息（导演、演员、剧情、评分等）
- chat: 闲聊、打招呼、感谢、询问你是谁等非任务型对话
- knowledge: 关于电影行业、历史、文化等知识性问题

分析原则：
1. 如果当前输入模糊（如"还有吗"、"换一批"），继承上轮的推荐意图
2. 如果用户说"新一点的"、"老电影"，提取 year 实体
3. 如果用户说"这个不错"、"不喜欢这个"，理解为对上一轮推荐电影的反馈
4. confidence 反映你对判断的把握程度

注意：只返回 JSON，不要其他内容。"""

        user_message = f"请分析以下用户输入的意图："
        if context_info:
            user_message += f"\n\n【历史对话】\n{context_info}"
        user_message += f"\n\n【当前输入】\n{user_input}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        try:
            if self.llm_router and self.llm_router._initialized:
                response = await self.llm_router.call_llm(messages)
                
                content = response.content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                
                intent_result = json.loads(content)
                
                if not isinstance(intent_result, dict):
                    raise ValueError("返回格式不正确")
                
                intent_result.setdefault("intent_type", "chat")
                intent_result.setdefault("needs_recommend", False)
                intent_result.setdefault("needs_search", False)
                intent_result.setdefault("confidence", 0.5)
                intent_result.setdefault("extracted_info", {})
                intent_result.setdefault("reasoning", "")
                
                return intent_result
            else:
                logger.warning("LLM 未初始化，使用默认降级方案")
                return self._get_default_intent_analysis(user_input)
                
        except Exception as e:
            logger.warning(f"LLM 意图分析失败，使用默认降级方案: {str(e)}")
            return self._get_default_intent_analysis(user_input)
    
    def _get_default_intent_analysis(self, user_input: str) -> Dict[str, Any]:
        """
        LLM 完全失败时的最低降级方案
        返回最保守的判断：当作闲聊处理
        """
        return {
            "intent_type": "chat",
            "needs_recommend": False,
            "needs_search": False,
            "confidence": 0.3,
            "extracted_info": {},
            "reasoning": "LLM 分析失败，默认按闲聊处理"
        }
    
    def _inherit_context_entities(
        self,
        recent_history: list,
        current_entities: Dict[str, Any],
        intent_type: str
    ) -> Dict[str, Any]:
        """
        从历史对话中继承实体
        
        Args:
            recent_history: 最近的对话历史
            current_entities: 当前输入提取的实体
            intent_type: 当前意图类型
        
        Returns:
            需要继承的实体字典
        """
        inherited = {}
        
        if intent_type == "chat":
            return inherited
        
        # 获取上一轮推荐的电影列表（从历史回复中提取）
        last_recommendation = None
        if recent_history:
            last_turn = recent_history[-1]
            if last_turn.intent == "recommend" and last_turn.context:
                last_recommendation = last_turn.context.get("recommended_movies")
        
        # 实体继承规则:
        # 1. genre: 如果当前没提类型，但历史有，则继承
        if not current_entities.get("genre"):
            for turn in reversed(recent_history):
                if turn.intent == "recommend" and turn.context.get("genre"):
                    inherited["genre"] = turn.context["genre"]
                    break
        
        # 2. mood/scene: 同上
        if not current_entities.get("mood"):
            for turn in reversed(recent_history):
                if turn.intent in ["recommend", "scene_recommend"] and turn.context.get("mood"):
                    inherited["mood"] = turn.context["mood"]
                    break
        
        # 3. year: 同上
        if not current_entities.get("year"):
            for turn in reversed(recent_history):
                if turn.intent == "recommend" and turn.context.get("year"):
                    inherited["year"] = turn.context["year"]
                    break
        
        # 4. 如果是"还有吗"、"换一批"等，继承上一轮的完整推荐上下文
        ambiguous_phrases = ["还有吗", "换一批", "再来点", "更多", "类似的", "还有类似的"]
        is_ambiguous = any(phrase in current_entities.get("other", "") for phrase in ambiguous_phrases)
        
        if is_ambiguous and last_recommendation:
            inherited["previous_recommendation"] = last_recommendation
        
        return inherited
    
    async def _execute_task_isolated(self, state: MultiAgentState, task: Dict) -> Dict[str, Any]:
        """
        执行单个子任务并返回独立结果（用于并行执行）
        
        创建独立的结果容器，避免并行任务互相干扰
        
        Args:
            state: 当前状态
            task: 任务描述
            
        Returns:
            包含 agent_results 的字典
        """
        agent_name = task.get("agent", "summary")
        description = task.get("description", "")
        
        logger.info("-" * 40)
        logger.info(f"[并行执行] {agent_name}")
        logger.info(f"   任务描述: {description}")
        
        agent = self._sub_agents.get(agent_name)
        if not agent:
            logger.warning(f"[错误] 未找到Agent: {agent_name}")
            return {
                "agent_results": [{
                    "agent_name": agent_name,
                    "success": False,
                    "data": None,
                    "error": f"Agent {agent_name} 不存在"
                }]
            }
        
        try:
            logger.info(f"   开始并行执行 {agent.name}...")
            result_state = await agent.execute(state)
            logger.info(f"   [成功] {agent_name} 并行执行成功")
            return {"agent_results": result_state.get("agent_results", [])}
                
        except Exception as e:
            logger.error(f"   [错误] 并行任务执行失败: {agent_name}", error=str(e))
            return {
                "agent_results": [{
                    "agent_name": agent_name,
                    "success": False,
                    "data": None,
                    "error": str(e)
                }]
            }
    
    async def _execute_task(self, state: MultiAgentState, task: Dict) -> MultiAgentState:
        """
        执行单个子任务（串行执行，修改原状态）
        
        Args:
            state: 当前状态
            task: 任务描述 {"agent": "recommend", "description": "推荐科幻电影"}
        """
        agent_name = task.get("agent", "summary")
        description = task.get("description", "")
        
        logger.info("-" * 40)
        logger.info(f"[执行子任务] {agent_name}")
        logger.info(f"   任务描述: {description}")
        
        agent = self._sub_agents.get(agent_name)
        if not agent:
            logger.warning(f"[错误] 未找到Agent: {agent_name}")
            state["agent_results"].append({
                "agent_name": agent_name,
                "success": False,
                "data": None,
                "error": f"Agent {agent_name} 不存在"
            })
            return state
        
        try:
            logger.info(f"   开始执行 {agent.name}...")
            state = await agent.execute(state)
            
            # 检查执行结果
            if state["agent_results"]:
                last_result = state["agent_results"][-1]
                if last_result.get("success"):
                    logger.info(f"   [成功] {agent_name} 执行成功")
                    if last_result.get("data"):
                        data = last_result["data"]
                        if isinstance(data, dict) and "items" in data:
                            logger.info(f"   [数据] 返回 {len(data['items'])} 个推荐项")
                        elif isinstance(data, dict) and "movies" in data:
                            logger.info(f"   [数据] 返回 {len(data['movies'])} 个搜索结果")
                else:
                    logger.warning(f"   [失败] {agent_name} 执行失败: {last_result.get('error')}")
            else:
                logger.warning(f"   [警告] {agent_name} 未返回结果")
                
        except Exception as e:
            logger.error(f"   [错误] 子任务执行失败: {agent_name}", error=str(e))
            state["agent_results"].append({
                "agent_name": agent_name,
                "success": False,
                "data": None,
                "error": str(e)
            })
        
        logger.info("-" * 40)
        return state
