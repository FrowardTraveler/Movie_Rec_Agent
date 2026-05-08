"""
记忆内存服务测试

测试 MemoryBank 的增删改查、分类记忆、过期清理、推荐保存
"""

import asyncio
import time

import pytest

from services.memory.memory_bank import MemoryBank, MemoryItem


@pytest.fixture
async def memory_bank():
    """创建内存模式的 MemoryBank"""
    bank = MemoryBank()
    await bank.initialize()
    yield bank
    await bank.clear("test_user")


async def test_add_and_get_memory(memory_bank):
    """测试添加和获取记忆"""
    await memory_bank.add("test_user", "favorite_genre", "scifi", category="preference")

    result = await memory_bank.get("test_user", "preference", "favorite_genre")
    assert result == "scifi"


async def test_get_nonexistent(memory_bank):
    """测试获取不存在的记忆"""
    result = await memory_bank.get("test_user", "preference", "nonexistent")
    assert result is None


async def test_get_all_category(memory_bank):
    """测试获取整个分类的记忆"""
    await memory_bank.add("test_user", "genre1", "scifi", category="preference")
    await memory_bank.add("test_user", "genre2", "action", category="preference")

    result = await memory_bank.get("test_user", "preference")
    assert isinstance(result, dict)
    assert result.get("genre1") == "scifi"
    assert result.get("genre2") == "action"


async def test_delete_memory(memory_bank):
    """测试删除记忆"""
    await memory_bank.add("test_user", "temp_key", "temp_value", category="context")

    await memory_bank.delete("test_user", "context", "temp_key")
    result = await memory_bank.get("test_user", "context", "temp_key")
    assert result is None


async def test_delete_category(memory_bank):
    """测试删除整个分类"""
    await memory_bank.add("test_user", "key1", "value1", category="context")
    await memory_bank.add("test_user", "key2", "value2", category="context")

    await memory_bank.delete("test_user", "context")
    result = await memory_bank.get("test_user", "context")
    assert result is None


async def test_clear_all(memory_bank):
    """测试清空所有记忆"""
    await memory_bank.add("test_user", "key1", "value1", category="context")
    await memory_bank.add("test_user", "key2", "value2", category="preference")

    await memory_bank.clear("test_user")

    result1 = await memory_bank.get("test_user", "context", "key1")
    result2 = await memory_bank.get("test_user", "preference", "key2")
    assert result1 is None
    assert result2 is None


async def test_memory_ttl_expiry(memory_bank):
    """测试记忆自动过期"""
    await memory_bank.add("test_user", "temp_key", "temp_value", category="context", ttl=1)

    result = await memory_bank.get("test_user", "context", "temp_key")
    assert result == "temp_value"

    await asyncio.sleep(1.1)

    result = await memory_bank.get("test_user", "context", "temp_key")
    assert result is None


async def test_save_recommendation(memory_bank):
    """测试保存推荐结果"""
    movies = [
        {"title": "Inception", "genres": "Sci-Fi", "year": 2010, "rating": 8.8},
        {"title": "Interstellar", "genres": "Sci-Fi", "year": 2014, "rating": 8.6},
    ]

    await memory_bank.save_recommendation(user_id="test_user", movies=movies, query="推荐科幻电影")

    result = await memory_bank.get("test_user", "recommendation", "last_recommendation")
    assert result is not None
    assert result["query"] == "推荐科幻电影"
    assert len(result["movies"]) == 2
    assert len(result["movie_names"]) == 2


async def test_save_preference(memory_bank):
    """测试保存用户偏好"""
    await memory_bank.save_preference("test_user", "favorite_genre", "scifi")

    result = await memory_bank.get("test_user", "preference", "favorite_genre")
    assert result == "scifi"


async def test_save_preference_merge_list(memory_bank):
    """测试保存偏好时自动合并为列表"""
    await memory_bank.save_preference("test_user", "genres", "scifi")
    await memory_bank.save_preference("test_user", "genres", "action")

    result = await memory_bank.get("test_user", "preference", "genres")
    assert isinstance(result, list)
    assert "scifi" in result
    assert "action" in result


async def test_get_recent(memory_bank):
    """测试获取最近 N 条记忆"""
    await memory_bank.add("test_user", "rec1", {"title": "Movie1"}, category="recommendation")
    await asyncio.sleep(0.1)
    await memory_bank.add("test_user", "rec2", {"title": "Movie2"}, category="recommendation")

    result = await memory_bank.get_recent("test_user", "recommendation", limit=1)
    assert len(result) == 1
    assert result[0]["title"] == "Movie2"


async def test_get_context_summary(memory_bank):
    """测试获取上下文摘要"""
    movies = [
        {"title": "Inception", "genres": "Sci-Fi", "year": 2010, "rating": 8.8},
    ]
    await memory_bank.save_recommendation("test_user", movies, "推荐科幻电影")
    await memory_bank.save_preference("test_user", "favorite_genre", "scifi")

    summary = await memory_bank.get_context_summary("test_user")

    assert "Inception" in summary
    assert "Sci-Fi" in summary
    assert "推荐科幻电影" in summary
    assert "scifi" in summary


async def test_get_context_summary_empty(memory_bank):
    """测试无记忆时返回空摘要"""
    summary = await memory_bank.get_context_summary("test_user")
    assert summary == ""


async def test_update_existing_memory(memory_bank):
    """测试更新已存在的记忆（替换旧值）"""
    await memory_bank.add("test_user", "last_query", "科幻电影", category="context")
    await memory_bank.add("test_user", "last_query", "动作电影", category="context")

    result = await memory_bank.get("test_user", "context", "last_query")
    assert result == "动作电影"


def test_memory_item_serialization():
    """测试 MemoryItem 序列化"""
    item = MemoryItem(
        key="test_key",
        value={"title": "Test Movie"},
        category="recommendation",
        timestamp=time.time(),
        ttl=3600,
    )

    d = item.to_dict()
    assert d["key"] == "test_key"
    assert d["value"] == {"title": "Test Movie"}
    assert d["category"] == "recommendation"

    restored = MemoryItem.from_dict(d)
    assert restored.key == item.key
    assert restored.value == item.value
    assert restored.category == item.category


async def test_multiple_users_isolation(memory_bank):
    """测试多用户记忆隔离"""
    await memory_bank.add("user1", "genre", "scifi", category="preference")
    await memory_bank.add("user2", "genre", "romance", category="preference")

    result1 = await memory_bank.get("user1", "preference", "genre")
    result2 = await memory_bank.get("user2", "preference", "genre")

    assert result1 == "scifi"
    assert result2 == "romance"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
