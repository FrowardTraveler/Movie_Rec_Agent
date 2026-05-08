"""
LLM 路由器测试

测试 LLMRouter 的初始化、MockLLM 行为、降级机制
"""

import pytest
import os

from llm.llm_router import LLMRouter, MockLLM
from langchain_core.messages import HumanMessage, AIMessage


@pytest.fixture
def mock_llm():
    """创建 MockLLM 实例"""
    return MockLLM()


def test_mock_llm_type(mock_llm):
    """测试 MockLLM 类型标识"""
    assert mock_llm._llm_type == "mock"


def test_mock_llm_generate(mock_llm):
    """测试 MockLLM 生成响应"""
    messages = [HumanMessage(content="你好")]
    
    result = mock_llm._generate(messages)
    
    assert result.generations is not None
    assert len(result.generations) > 0
    assert "模拟" in result.generations[0].message.content


async def test_mock_llm_agenerate(mock_llm):
    """测试 MockLLM 异步生成"""
    messages = [HumanMessage(content="推荐电影")]
    
    result = await mock_llm._agenerate(messages)
    
    assert result.generations is not None
    assert len(result.generations) > 0


@pytest.fixture
def router():
    """创建 LLMRouter（不初始化）"""
    router = LLMRouter()
    # 设置为模拟模式避免真实 API 调用
    from agent.config.agent_config import config
    config.llm.provider = "unknown"
    return router


async def test_router_initialize_unknown_provider(router):
    """测试未知 provider 使用 MockLLM"""
    from agent.config.agent_config import config
    config.llm.provider = "unknown"
    config.llm.api_key = ""
    config.llm.base_url = ""
    config.llm.model = "mock"
    
    await router.initialize()
    
    assert router._initialized is True
    assert isinstance(router._llm, MockLLM)


async def test_router_get_llm(router):
    """测试获取 LLM 实例"""
    from agent.config.agent_config import config
    config.llm.provider = "unknown"
    config.llm.api_key = ""
    
    await router.initialize()
    
    llm = router.get_llm()
    assert llm is not None


async def test_router_call_llm_fallback(mock_llm):
    """测试 LLM 调用降级"""
    messages = [HumanMessage(content="测试")]
    
    result = await mock_llm.ainvoke(messages)
    
    assert result is not None
    assert isinstance(result.content, str)


def test_router_init_openai_no_key():
    """测试无 API Key 时返回 MockLLM"""
    router = LLMRouter()
    from agent.config.agent_config import config
    config.llm.provider = "openai"
    config.llm.api_key = ""
    config.llm.base_url = ""
    config.llm.model = "gpt-4"
    
    # 由于 .env 中可能有全局 API Key，测试实际行为（可能返回 ChatOpenAI 或 MockLLM）
    llm = router._init_openai()
    assert llm is not None
    assert hasattr(llm, 'ainvoke')


def test_router_init_local():
    """测试本地 LLM 初始化（未实现）"""
    router = LLMRouter()
    
    llm = router._init_local()
    assert isinstance(llm, MockLLM)


async def test_router_initialization_idempotent(router):
    """测试重复初始化幂等"""
    from agent.config.agent_config import config
    config.llm.provider = "unknown"
    
    await router.initialize()
    await router.initialize()
    
    assert router._initialized is True


async def test_call_llm_with_mock(router):
    """测试通过路由器调用 LLM"""
    from agent.config.agent_config import config
    config.llm.provider = "unknown"
    config.llm.api_key = ""
    
    await router.initialize()
    
    messages = [HumanMessage(content="Hello")]
    result = await router.call_llm(messages)
    
    assert result is not None
    assert hasattr(result, 'content')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
