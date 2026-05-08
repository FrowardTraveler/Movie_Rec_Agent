"""
推荐引擎适配器测试

验证推荐引擎适配器的基本功能
"""

import pytest

from services.recommendation.engine_adapter import (
    MockRecommendationEngine,
    RecommendationEngineAdapter,
)


@pytest.fixture
def engine():
    """创建推荐引擎适配器"""
    return RecommendationEngineAdapter()


@pytest.fixture
def mock_engine():
    """创建模拟推荐引擎"""
    return MockRecommendationEngine()


@pytest.mark.asyncio
async def test_mock_engine_recommend(mock_engine):
    """测试模拟推荐引擎"""
    user_features = {"user_id": "test_user"}
    result = await mock_engine.recommend(user_features, top_k=5)

    assert len(result) == 5
    assert all("title" in movie for movie in result)
    assert all("id" in movie for movie in result)
    assert all("rating" in movie for movie in result)


@pytest.mark.asyncio
async def test_engine_adapter_initialize(engine):
    """测试引擎适配器初始化"""
    await engine.initialize()
    assert engine._initialized is True


@pytest.mark.asyncio
async def test_engine_adapter_get_recommendations(engine):
    """测试引擎适配器获取推荐"""
    result = await engine.get_recommendations(
        user_id="test_user", context={"mood": "happy"}, top_k=5
    )

    assert isinstance(result, list)
    assert len(result) > 0
    assert all("title" in movie for movie in result)


@pytest.mark.asyncio
async def test_engine_adapter_fallback(engine):
    """测试引擎适配器降级推荐"""
    result = await engine._fallback_recommendations(user_id="test_user", top_k=3)

    assert len(result) == 3
    assert all("title" in movie for movie in result)
    assert all("popular" in movie["id"] for movie in result)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
