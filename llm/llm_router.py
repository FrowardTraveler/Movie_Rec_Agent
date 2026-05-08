"""
LLM 路由器

管理不同的 LLM 提供商，支持切换和降级
"""

import os
from typing import Optional

import structlog
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from agent.config.agent_config import config
from services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger()


class LLMRouter:
    """
    LLM 路由器
    
    管理不同的 LLM 提供商，支持热切换
    """
    
    def __init__(self):
        """初始化 LLM 路由器"""
        self.llm_config = config.llm
        self._llm: Optional[BaseChatModel] = None
        self._initialized = False
        self._circuit_breaker = CircuitBreaker(
            name="LLM服务",
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=2
        )
    
    async def initialize(self):
        """
        初始化 LLM
        
        根据配置选择合适的 LLM 提供商
        """
        if self._initialized:
            return
        
        try:
            # 从环境变量读取配置
            self.llm_config.api_key = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", ""))
            self.llm_config.base_url = os.getenv("LLM_BASE_URL", os.getenv("OPENAI_API_BASE", ""))
            model_id = os.getenv("MODEL_NAME", os.getenv("LLM_MODEL_ID", ""))
            if model_id:
                self.llm_config.model = model_id
            
            provider = self.llm_config.provider
            
            if provider == "openai":
                self._llm = self._init_openai()
            elif provider == "local":
                self._llm = self._init_local()
            else:
                logger.warning(f"不支持的 LLM 提供商: {provider}，使用模拟模式")
                self._llm = MockLLM()
            
            self._initialized = True
            logger.info("LLM 初始化完成", provider=provider, model=self.llm_config.model)
            
        except Exception as e:
            logger.warning(f"LLM 初始化失败: {e}，使用模拟模式")
            self._llm = MockLLM()
            self._initialized = True
    
    def _init_openai(self) -> BaseChatModel:
        """
        初始化 OpenAI LLM（支持兼容 OpenAI 接口的服务）
        
        Returns:
            OpenAI LLM 实例
        """
        api_key = self.llm_config.api_key or os.getenv("LLM_API_KEY", "")
        
        if not api_key:
            logger.warning("未设置 LLM_API_KEY 环境变量，使用模拟模式")
            return MockLLM()
        
        base_url = self.llm_config.base_url or os.getenv("LLM_BASE_URL", "")
        
        kwargs = {
            "model": self.llm_config.model,
            "temperature": self.llm_config.temperature,
            "max_tokens": self.llm_config.max_tokens,
            "api_key": api_key,
        }
        
        if base_url:
            kwargs["base_url"] = base_url
            logger.info("使用自定义 base_url", url=base_url)
        
        return ChatOpenAI(**kwargs)
    
    def _init_local(self) -> BaseChatModel:
        """
        初始化本地 LLM
        
        Returns:
            本地 LLM 实例
        """
        # MVP 版本使用模拟实现
        # TODO: 实现 Ollama/vLLM 集成
        logger.info("本地 LLM 暂未实现，使用模拟模式")
        return MockLLM()
    
    def get_llm(self) -> BaseChatModel:
        """
        获取 LLM 实例
        
        Returns:
            LLM 实例
        """
        if not self._initialized:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.initialize())
        
        return self._llm
    
    async def call_llm(self, messages: list[BaseMessage], **kwargs):
        """
        通过熔断器调用 LLM
        
        Args:
            messages: 消息列表
            **kwargs: 额外参数传递给 ainvoke
            
        Returns:
            LLM 响应
            
        Notes:
            当熔断器打开时，自动降级到 MockLLM
        """
        try:
            return await self._circuit_breaker.call(
                self._llm.ainvoke,
                messages,
                **kwargs
            )
        except CircuitBreakerOpenError as e:
            logger.warning(f"LLM 服务已熔断，降级到 MockLLM", remaining=e.remaining_seconds)
            return await MockLLM().ainvoke(messages, **kwargs)
        except Exception as e:
            logger.error(f"LLM 调用异常: {e}，尝试使用 MockLLM")
            try:
                return await MockLLM().ainvoke(messages, **kwargs)
            except Exception as fallback_error:
                logger.error(f"MockLLM 也失败了: {fallback_error}")
                raise


class MockLLM(BaseChatModel):
    """
    模拟 LLM（用于 MVP 阶段）
    
    当没有配置真实 LLM 时使用
    """
    
    @property
    def _llm_type(self) -> str:
        return "mock"
    
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """模拟生成"""
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatResult, ChatGeneration
        
        response_text = "我是模拟 LLM，用于 MVP 阶段测试。"
        
        message = AIMessage(content=response_text)
        generation = ChatGeneration(message=message)
        
        return ChatResult(generations=[generation])
    
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        """异步模拟生成"""
        return self._generate(messages, stop, run_manager, **kwargs)
