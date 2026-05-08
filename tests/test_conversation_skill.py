"""
对话技能测试

验证对话技能的基本功能
"""

import pytest

from skills.conversation.conversation_skill import ConversationSkill


@pytest.fixture
def conversation_skill():
    """创建对话技能实例"""
    return ConversationSkill()


def test_classify_greeting(conversation_skill):
    """测试问候意图分类"""
    intent = conversation_skill._classify_intent("你好")
    assert intent == "greeting"

    intent = conversation_skill._classify_intent("嗨")
    assert intent == "greeting"


def test_classify_emotion(conversation_skill):
    """测试情感意图分类"""
    intent = conversation_skill._classify_intent("我今天很开心")
    assert intent == "emotion"

    intent = conversation_skill._classify_intent("心情不好")
    assert intent == "emotion"


def test_classify_follow_up(conversation_skill):
    """测试追问意图分类"""
    intent = conversation_skill._classify_intent("还有吗")
    assert intent == "follow_up"

    intent = conversation_skill._classify_intent("换一个")
    assert intent == "follow_up"


def test_fallback_greeting(conversation_skill):
    """测试问候降级响应"""
    response = conversation_skill._get_fallback_response("你好", "greeting")
    assert "你好" in response or "嗨" in response or "电影" in response


def test_fallback_emotion(conversation_skill):
    """测试情感降级响应"""
    response = conversation_skill._get_fallback_response("我今天很开心", "emotion")
    assert "心情" in response or "电影" in response or "放松" in response


@pytest.mark.asyncio
async def test_execute_conversation(conversation_skill):
    """测试对话技能执行"""
    result = await conversation_skill.execute(user_input="你好", user_id="test_user")

    assert result["success"] is True
    assert "response" in result
    assert result["intent"] == "greeting"
    assert result["skill"] == "conversation_skill"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
