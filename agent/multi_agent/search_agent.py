"""
搜索Agent - 信息检索专家

负责搜索电影的详细信息
"""

from typing import Dict, Any, List

from agent.multi_agent import BaseAgent, MultiAgentState
from skills.search.search_skill import SearchSkill
from llm.llm_router import LLMRouter

import structlog

logger = structlog.get_logger()


class SearchAgent(BaseAgent):
    """
    搜索Agent - 信息检索专家
    
    职责：
    - 搜索电影的详细信息
    - 使用本地 JSON 数据源搜索
    - 使用搜索引擎补充
    - 使用LLM整合搜索结果
    """
    
    name: str = "search_agent"
    description: str = "信息检索专家 - 搜索电影详细信息"
    
    def __init__(self, llm_router=None):
        super().__init__(llm_router)
        self.search_skill = SearchSkill()
    
    async def initialize(self):
        """初始化搜索Agent"""
        if self._initialized:
            return
        
        self._initialized = True
        logger.info("搜索Agent初始化完成")
    
    async def execute(self, state: MultiAgentState) -> MultiAgentState:
        """执行搜索任务"""
        try:
            logger.info("[SearchAgent] 开始执行")
            logger.info(f"   用户输入: {state['user_input']}")
            
            # 使用搜索技能
            search_result = await self.search_skill.execute(
                query=state["user_input"],
                user_id=state["user_id"],
                top_k=5
            )
            
            if search_result.get("success"):
                results = search_result.get("data", {}).get("results", [])
                logger.info(f"   [结果] 搜索到 {len(results)} 条结果")
                
                state["agent_results"].append({
                    "agent_name": self.name,
                    "success": True,
                    "data": {
                        "source": "search",
                        "movies": results,
                        "response": search_result.get("response", "")
                    },
                    "error": None
                })
                logger.info("   [成功] SearchAgent 执行成功")
            else:
                logger.warning("   [失败] 搜索未找到结果")
                state["agent_results"].append({
                    "agent_name": self.name,
                    "success": False,
                    "data": {"source": "none", "movies": []},
                    "error": "未找到相关信息"
                })
            
            return state
            
        except Exception as e:
            logger.error(f"   [异常] SearchAgent 执行异常: {str(e)}")
            state["agent_results"].append({
                "agent_name": self.name,
                "success": False,
                "data": None,
                "error": str(e)
            })
            return state
