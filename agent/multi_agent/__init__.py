"""
多Agent协同架构

主Agent + 专业Agent协作模式
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from dotenv import load_dotenv

# 加载 .env 文件
env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

import structlog

logger = structlog.get_logger()


# ==================== 共享状态定义 ====================

class AgentResult(TypedDict):
    """Agent执行结果"""
    agent_name: str
    success: bool
    data: Any
    error: Optional[str]


class MultiAgentState(TypedDict):
    """多Agent共享状态"""
    user_input: str
    user_id: str
    task_plan: List[Dict]  # 任务计划
    agent_results: List[AgentResult]  # 各Agent执行结果
    final_response: str  # 最终回复
    messages: Sequence[BaseMessage]  # 对话历史
    current_step: int  # 当前步骤
    error: Optional[str]  # 错误信息
    intent_analysis: Dict[str, Any]  # 意图分析结果
    react_logs: List[Dict]  # ReAct 推理循环日志
    react_iterations: int  # ReAct 循环次数
    react_max_iterations_reached: bool  # 是否达到最大迭代次数
    memory_context: str  # 记忆内存上下文（上次推荐、用户偏好等）


# ==================== Agent基类 ====================

class BaseAgent:
    """Agent基类"""
    
    name: str = "base_agent"
    description: str = "基础Agent"
    
    def __init__(self, llm_router=None):
        self.llm_router = llm_router
        self._initialized = False
    
    async def initialize(self):
        """初始化Agent"""
        self._initialized = True
        logger.info(f"{self.name} 初始化完成")
    
    async def execute(self, state: MultiAgentState) -> MultiAgentState:
        """
        执行Agent任务
        
        Args:
            state: 多Agent共享状态
            
        Returns:
            更新后的状态
        """
        raise NotImplementedError
