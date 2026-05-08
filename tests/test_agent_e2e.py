"""
端到端集成测试

验证 Agent 的完整流程，包括意图识别、技能选择、执行和响应生成
"""

import pytest
from agent.agent import MovieRecommendAgent


@pytest.fixture
async def agent():
    """创建并初始化 Agent"""
    test_agent = MovieRecommendAgent()
    await test_agent.initialize()
    return test_agent


async def test_recommend_intent(agent):
    """测试推荐意图识别和执行"""
    result = await agent.invoke(
        user_input="推荐几部电影",
        user_id="test_user_001"
    )
    
    assert "response" in result
    assert result["intent"] == "recommend"
    assert len(result.get("response", "")) > 0
    assert result.get("latency_ms", 0) > 0
    print(f"推荐响应延迟: {result['latency_ms']}ms")


async def test_greeting_intent(agent):
    """测试问候意图识别和处理"""
    result = await agent.invoke(
        user_input="你好",
        user_id="test_user_001"
    )
    
    assert "response" in result
    assert result["intent"] == "conversation"
    assert "你好" in result["response"] or "嗨" in result["response"]


async def test_emotion_intent(agent):
    """测试情感意图识别和处理"""
    result = await agent.invoke(
        user_input="我今天很开心",
        user_id="test_user_001"
    )
    
    assert "response" in result
    assert result["intent"] == "conversation"
    assert "心情" in result["response"] or "电影" in result["response"]


async def test_fallback_response(agent):
    """测试降级响应（当输入无法识别时）"""
    result = await agent.invoke(
        user_input="asdfghjkl",
        user_id="test_user_001"
    )
    
    assert "response" in result
    assert len(result["response"]) > 0


async def test_recommend_with_context(agent):
    """测试带上下文的推荐"""
    result = await agent.invoke(
        user_input="推荐一些浪漫的爱情电影",
        user_id="test_user_001"
    )
    
    assert result["intent"] == "recommend"
    assert "response" in result
    assert len(result["response"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
