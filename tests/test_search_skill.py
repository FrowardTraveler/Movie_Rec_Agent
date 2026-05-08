"""
搜索技能测试

验证搜索技能的基本功能
"""

import pytest
from skills.search.search_skill import SearchSkill


@pytest.fixture
def search_skill():
    """创建搜索技能实例"""
    return SearchSkill()


def test_search_skill_name(search_skill):
    """测试搜索技能名称"""
    assert search_skill.name == "search_skill"


def test_search_skill_description(search_skill):
    """测试搜索技能描述"""
    assert len(search_skill.description) > 0


def test_search_skill_priority(search_skill):
    """测试搜索技能优先级"""
    assert search_skill.priority == 1  # 高优先级


async def test_search_execution(search_skill):
    """测试搜索技能执行"""
    result = await search_skill.execute(
        query="复仇者联盟",
        user_id="test_user",
        top_k=3
    )
    
    assert result["success"] is True
    assert "response" in result
    assert "复仇者联盟" in result["response"]
    assert result["skill"] == "search_skill"


async def test_search_empty_query(search_skill):
    """测试空查询"""
    result = await search_skill.execute(
        query="",
        user_id="test_user",
        top_k=5
    )
    
    assert result["success"] is True
    assert "response" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
