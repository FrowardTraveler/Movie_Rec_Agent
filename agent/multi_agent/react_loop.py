"""
ReAct 推理循环控制器

实现 Thought-Action-Observation-Reflection 循环
让 Agent 具备自我反思和动态调整能力
"""

import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from agent.multi_agent import MultiAgentState
from llm.llm_router import LLMRouter

import structlog

logger = structlog.get_logger()


class ReActLoop:
    """
    ReAct 推理循环控制器
    
    核心流程：
    1. Thought: 分析当前状态和用户需求
    2. Action: 执行子任务（推荐、搜索等）
    3. Observation: 检查结果质量
    4. Reflection: 反思结果是否满意
    5. 如果不满意，调整策略并继续循环
    
    最多循环 MAX_ITERATIONS 次，防止无限循环
    """
    
    MAX_ITERATIONS = 3
    
    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router
    
    async def execute_with_reflection(
        self,
        state: MultiAgentState,
        task_plan: List[Dict],
        execute_task_fn,
        execute_task_isolated_fn
    ) -> MultiAgentState:
        """
        带反思的任务执行循环
        
        Args:
            state: 多Agent共享状态
            task_plan: 任务计划列表
            execute_task_fn: 串行执行任务的函数引用
            execute_task_isolated_fn: 并行执行独立任务的函数引用
        
        Returns:
            更新后的状态
        """
        import asyncio
        
        for iteration in range(self.MAX_ITERATIONS):
            # [Thought] 思考当前状态
            thought = await self._generate_thought(state, iteration)
            logger.info(f"[ReAct Thought {iteration+1}/{self.MAX_ITERATIONS}] {thought}")
            state.setdefault("react_logs", []).append({
                "iteration": iteration + 1,
                "type": "thought",
                "content": thought
            })
            
            # [Action] 执行任务
            state = await self._execute_tasks(
                state, task_plan, execute_task_fn, execute_task_isolated_fn
            )
            
            # [Observation] 观察结果
            observation = self._observe_results(state.get("agent_results", []))
            logger.info(f"[ReAct Observation {iteration+1}/{self.MAX_ITERATIONS}] {observation}")
            state.setdefault("react_logs", []).append({
                "iteration": iteration + 1,
                "type": "observation",
                "content": observation
            })
            
            # [Reflection] 反思：结果是否满意？
            reflection = await self._reflect_on_results(state, observation)
            logger.info(f"[ReAct Reflection {iteration+1}/{self.MAX_ITERATIONS}] {reflection}")
            state.setdefault("react_logs", []).append({
                "iteration": iteration + 1,
                "type": "reflection",
                "content": reflection
            })
            
            if reflection["satisfied"]:
                logger.info(f"[ReAct Result] 第 {iteration+1} 次循环结果满意，退出循环")
                state["react_iterations"] = iteration + 1
                break
            
            # [Adjust] 调整策略（如果不是最后一次）
            if iteration < self.MAX_ITERATIONS - 1:
                task_plan = reflection.get("adjusted_plan", task_plan)
                logger.info(f"[ReAct Adjust] 调整任务计划: {task_plan}")
                
                # 清空之前的失败结果，准备重试
                state["agent_results"] = [
                    r for r in state.get("agent_results", [])
                    if r.get("success")
                ]
            else:
                logger.warning(f"[ReAct Result] 达到最大迭代次数({self.MAX_ITERATIONS})，使用当前结果")
                state["react_iterations"] = self.MAX_ITERATIONS
                state["react_max_iterations_reached"] = True
        
        return state
    
    async def _generate_thought(self, state: MultiAgentState, iteration: int) -> str:
        """
        生成思考内容
        
        第1次：分析用户需求
        后续：基于上次结果调整策略
        """
        if iteration == 0:
            user_input = state.get("user_input", "")
            intent = state.get("intent_analysis", {}).get("intent_type", "unknown")
            return f"分析用户需求: '{user_input}'，意图类型: {intent}"
        else:
            prev_results = state.get("agent_results", [])
            success_count = sum(1 for r in prev_results if r.get("success"))
            return f"第 {iteration} 次循环，前次成功 {success_count}/{len(prev_results)} 个任务，需要调整策略"
    
    async def _execute_tasks(
        self,
        state: MultiAgentState,
        task_plan: List[Dict],
        execute_task_fn,
        execute_task_isolated_fn
    ) -> MultiAgentState:
        """
        执行任务计划
        
        分离独立任务和依赖任务，并行执行独立任务
        """
        import asyncio
        
        independent_tasks = []
        dependent_tasks = []
        
        for task in task_plan:
            if task.get("agent") == "summary":
                dependent_tasks.append(task)
            else:
                independent_tasks.append(task)
        
        # 并行执行独立任务
        if independent_tasks:
            logger.info(f"   [ReAct Action] 并行执行 {len(independent_tasks)} 个任务...")
            parallel_results = await asyncio.gather(
                *[execute_task_isolated_fn(state, task) for task in independent_tasks],
                return_exceptions=True
            )
            
            for i, result in enumerate(parallel_results):
                if isinstance(result, Exception):
                    task = independent_tasks[i]
                    logger.error(f"   [ReAct Action 异常] {task['agent']}", error=str(result))
                    state["agent_results"].append({
                        "agent_name": task["agent"],
                        "success": False,
                        "data": None,
                        "error": str(result)
                    })
                else:
                    state["agent_results"].extend(result.get("agent_results", []))
        
        # 串行执行依赖任务
        for task in dependent_tasks:
            state = await execute_task_fn(state, task)
        
        return state
    
    def _observe_results(self, agent_results: List[Dict]) -> Dict[str, Any]:
        """
        观察结果质量
        
        检查项：
        - 任务执行成功率
        - 推荐结果数量
        - 推荐验证通过率
        - 错误信息
        """
        observation = {
            "success_count": 0,
            "failure_count": 0,
            "total_items": 0,
            "verified_items": 0,
            "unverified_items": 0,
            "issues": []
        }
        
        for result in agent_results:
            agent_name = result.get("agent_name", "unknown")
            
            if result.get("success"):
                observation["success_count"] += 1
                
                data = result.get("data", {})
                
                # 检查推荐结果
                if agent_name == "recommend_agent":
                    items = data.get("items", [])
                    observation["total_items"] += len(items)
                    
                    source = data.get("source", "")
                    if source == "llm_kb_verified":
                        observation["verified_items"] += len(items)
                    elif source == "llm_fallback_unverified":
                        observation["unverified_items"] += len(items)
                    
                    if len(items) == 0:
                        observation["issues"].append("推荐结果为空")
                    elif len(items) < 3:
                        observation["issues"].append(f"推荐结果不足({len(items)}部<3部)")
                
                # 检查结果来源
                if data.get("source") == "llm_fallback_unverified":
                    observation["issues"].append("所有推荐都未在数据库中找到")
            else:
                observation["failure_count"] += 1
                error_msg = result.get("error", "未知错误")
                observation["issues"].append(f"{agent_name} 执行失败: {error_msg}")
        
        return observation
    
    async def _reflect_on_results(
        self,
        state: MultiAgentState,
        observation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        使用 LLM 反思结果质量
        
        返回：
        - satisfied: 是否满意
        - reason: 原因
        - adjustment_strategy: 调整策略
        - need_retry: 是否需要重试
        - adjusted_plan: 调整后的任务计划
        """
        
        # 快速判断：如果结果很好，直接满意
        if (observation["success_count"] > 0 and 
            observation["failure_count"] == 0 and
            observation["total_items"] >= 3 and
            len(observation["issues"]) == 0):
            return {
                "satisfied": True,
                "reason": "结果质量优秀，所有任务成功且推荐充足"
            }
        
        # 如果有严重问题，使用 LLM 分析
        if not self.llm_router or not self.llm_router._initialized:
            # LLM 未初始化，使用规则判断
            return self._reflect_with_rules(state, observation)
        
        system_prompt = """你是一个 Agent 执行质量评估专家。

根据执行结果和观察到的问题，判断是否需要重新执行任务。

返回 JSON 格式：
{
    "satisfied": true/false,
    "reason": "简短原因（1句话）",
    "adjustment_strategy": "调整策略（放宽条件/换关键词/降级方案/无需调整）",
    "need_retry": true/false
}

判断标准：
- 所有任务成功且推荐>=3部 → satisfied=true
- 推荐结果太少 → 放宽条件（去掉心情、年份等限制）
- 所有推荐未验证 → 降级到传统推荐系统
- 任务执行失败 → 重试或降级
- 搜索未找到 → 换关键词

注意：只返回 JSON，不要其他内容。"""
        
        user_input = state.get("user_input", "")
        intent = state.get("intent_analysis", {})
        
        user_message = f"""
【用户原始需求】{user_input}
【意图分析】{json.dumps(intent, ensure_ascii=False)}
【执行结果】
- 成功任务: {observation['success_count']}
- 失败任务: {observation['failure_count']}
- 推荐总数: {observation['total_items']}
- 已验证: {observation['verified_items']}
- 未验证: {observation['unverified_items']}
- 问题列表: {', '.join(observation['issues']) if observation['issues'] else '无'}

请分析是否需要重新执行任务，以及如何调整。
"""
        
        try:
            response = await self.llm_router.call_llm([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])
            
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            
            reflection = json.loads(content)
            
            # 如果需要重试，生成调整后的计划
            if reflection.get("need_retry"):
                reflection["adjusted_plan"] = self._generate_adjusted_plan(
                    state, reflection.get("adjustment_strategy", "")
                )
            else:
                reflection["satisfied"] = True
            
            return reflection
            
        except Exception as e:
            logger.warning(f"LLM 反思失败，使用规则降级: {str(e)}")
            return self._reflect_with_rules(state, observation)
    
    def _reflect_with_rules(
        self,
        state: MultiAgentState,
        observation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        基于规则的反思（LLM 不可用时的降级方案）
        """
        issues = observation["issues"]
        
        # 如果推荐结果为空或太少
        if observation["total_items"] < 3:
            return {
                "satisfied": False,
                "reason": "推荐结果不足",
                "adjustment_strategy": "放宽条件",
                "need_retry": True,
                "adjusted_plan": self._generate_adjusted_plan(state, "放宽条件")
            }
        
        # 如果所有推荐都未验证
        if observation["unverified_items"] > 0 and observation["verified_items"] == 0:
            return {
                "satisfied": False,
                "reason": "所有推荐都未在数据库中找到",
                "adjustment_strategy": "降级方案",
                "need_retry": True,
                "adjusted_plan": self._generate_adjusted_plan(state, "降级方案")
            }
        
        # 如果有任务失败
        if observation["failure_count"] > 0:
            return {
                "satisfied": False,
                "reason": f"{observation['failure_count']} 个任务执行失败",
                "adjustment_strategy": "降级方案",
                "need_retry": True,
                "adjusted_plan": self._generate_adjusted_plan(state, "降级方案")
            }
        
        # 默认满意
        return {
            "satisfied": True,
            "reason": "结果可接受"
        }
    
    def _generate_adjusted_plan(
        self,
        state: MultiAgentState,
        adjustment_strategy: str
    ) -> List[Dict]:
        """
        根据调整策略生成新的任务计划
        
        策略：
        - 放宽条件: 去掉心情、年份等限制
        - 换关键词: 使用原始用户输入作为搜索词
        - 降级方案: 使用传统推荐系统
        """
        intent_analysis = state.get("intent_analysis", {})
        extracted_info = intent_analysis.get("extracted_info", {})
        user_input = state.get("user_input", "")
        
        adjusted_plan = []
        
        # 检查原始计划中是否有 recommend 任务
        has_recommend = any(t.get("agent") == "recommend" for t in state.get("task_plan", []))
        has_search = any(t.get("agent") == "search" for t in state.get("task_plan", []))
        
        if "放宽条件" in adjustment_strategy:
            # 放宽推荐条件
            if has_recommend:
                relaxed_info = {
                    "genre": extracted_info.get("genre", ""),
                    "other": "用户要求推荐电影"
                }
                
                desc_parts = ["推荐电影（放宽条件）"]
                if relaxed_info["genre"]:
                    desc_parts.append(f"类型: {relaxed_info['genre']}")
                
                adjusted_plan.append({
                    "agent": "recommend",
                    "description": " - ".join(desc_parts),
                    "params": relaxed_info
                })
                logger.info(f"   [放宽条件] 推荐参数: {relaxed_info}")
        
        elif "降级方案" in adjustment_strategy:
            # 使用传统推荐系统（通过 backend API）
            if has_recommend:
                adjusted_plan.append({
                    "agent": "recommend",
                    "description": "使用传统推荐系统推荐（降级方案）",
                    "params": {"use_traditional": True, **extracted_info}
                })
                logger.info("   [降级方案] 切换到传统推荐系统")
        
        elif "换关键词" in adjustment_strategy:
            # 使用原始用户输入作为搜索词
            if has_search:
                adjusted_plan.append({
                    "agent": "search",
                    "description": f"搜索电影信息: {user_input}",
                    "params": {"movie_name": user_input}
                })
                logger.info(f"   [换关键词] 搜索词: {user_input}")
        
        # 如果没有任何调整，保持原计划
        if not adjusted_plan:
            return state.get("task_plan", [])
        
        # 添加 SummaryAgent
        adjusted_plan.append({"agent": "summary", "description": "整合结果生成回复"})
        
        return adjusted_plan
