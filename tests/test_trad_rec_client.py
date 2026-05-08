"""
传统推荐客户端测试

测试 TraditionalRecommendationClient 的 URL 配置、超时、熔断、降级
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.integration.trad_rec_client import (
    TraditionalRecommendationClient,
    RecommendationItem,
)


@pytest.fixture
def client():
    """创建测试用客户端"""
    return TraditionalRecommendationClient(base_url="http://test:8000")


def test_recommendation_item_creation():
    """测试 RecommendationItem 创建"""
    item = RecommendationItem(
        movie_id=1,
        title="Test Movie",
        genres=["Action"],
        score=0.9,
    )
    assert item.movie_id == 1
    assert item.title == "Test Movie"
    assert item.genres == ["Action"]
    assert item.score == 0.9


def test_recommendation_item_optional_fields():
    """测试 RecommendationItem 可选字段"""
    item = RecommendationItem(
        movie_id=1,
        title="Test",
        genres=[],
        score=0.0,
        recall_type="youtubednn",
        poster_url="http://img.png",
        reason="测试",
    )
    assert item.recall_type == "youtubednn"
    assert item.poster_url == "http://img.png"
    assert item.reason == "测试"


async def test_client_initialization(client):
    """测试客户端初始化"""
    assert client.base_url == "http://test:8000"
    assert client._initialized is False
    assert client._session is None

    await client.initialize()
    assert client._initialized is True
    assert client._session is not None

    await client.close()
    assert client._initialized is False


async def test_client_timeout_config():
    """测试超时配置（验证默认值）"""
    from services.integration.trad_rec_client import (
        _HTTP_CONNECT_TIMEOUT,
        _HTTP_TOTAL_TIMEOUT,
    )
    assert _HTTP_CONNECT_TIMEOUT == 5
    assert _HTTP_TOTAL_TIMEOUT == 15

    client = TraditionalRecommendationClient()
    assert client._timeout.connect == 5
    assert client._timeout.total == 15


async def test_client_circuit_breaker_config(client):
    """测试熔断器配置"""
    assert client._circuit_breaker.name == "trad_rec_client"
    assert client._circuit_breaker.failure_threshold == 5
    assert client._circuit_breaker.recovery_timeout == 60
    assert client._circuit_breaker.success_threshold == 2


@pytest.mark.asyncio
async def test_get_recommendations_mock_session(client):
    """测试获取推荐结果（模拟 HTTP）"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "items": [
            {
                "movie_id": 1,
                "title": "Test Movie",
                "genres": ["Action"],
                "score": 0.9,
                "recall_type": "youtubednn",
            }
        ],
        "ranking_strategy": "deepfm",
    })
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    results = await client.get_recommendations(user_id="1", top_k=10)

    assert len(results) == 1
    assert results[0].movie_id == 1
    assert results[0].title == "Test Movie"
    assert results[0].recall_type == "youtubednn"


@pytest.mark.asyncio
async def test_get_recommendations_non_200(client):
    """测试推荐 API 返回非 200 状态"""
    mock_response = MagicMock()
    mock_response.status = 503
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    results = await client.get_recommendations(user_id="1")
    assert results == []


@pytest.mark.asyncio
async def test_search_movie_by_title_mock(client):
    """测试搜索电影（模拟 HTTP）"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[
        {"movie_id": 1, "title": "Test Movie", "genres": ["Action"]},
        {"movie_id": 2, "title": "Another Movie", "genres": ["Drama"]},
    ])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    result = await client.search_movie_by_title("Test Movie")

    assert result is not None
    assert result["movie_id"] == 1
    assert result["title"] == "Test Movie"


@pytest.mark.asyncio
async def test_search_movie_by_title_exact_match(client):
    """测试精确匹配优先"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[
        {"movie_id": 1, "title": "Another Test", "genres": []},
        {"movie_id": 2, "title": "Test Movie", "genres": ["Action"]},
    ])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    # 搜索 "Test Movie" 应该优先匹配到第二个
    result = await client.search_movie_by_title("Test Movie")

    assert result is not None
    assert result["movie_id"] == 2
    assert result["title"] == "Test Movie"


@pytest.mark.asyncio
async def test_search_movie_by_title_empty(client):
    """测试搜索无结果"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    result = await client.search_movie_by_title("Nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_llm_movie_ids(client):
    """测试 LLM 电影 ID 解析"""
    # 模拟搜索方法
    client.search_movie_by_title = AsyncMock(return_value={
        "movie_id": 42,
        "title": "Resolved Movie",
        "genres": ["Sci-Fi"],
        "imdb_rating": 8.5,
    })
    client._initialized = True

    llm_items = [
        {"title": "Test Movie", "score": 9.0, "reason": "推荐"},
    ]

    resolved = await client.resolve_llm_movie_ids(llm_items)

    assert len(resolved) == 1
    assert resolved[0]["movie_id"] == 42
    assert resolved[0]["title"] == "Resolved Movie"
    assert resolved[0]["source"] == "llm_fallback_resolved"
    assert resolved[0]["reason"] == "推荐"


@pytest.mark.asyncio
async def test_resolve_llm_movie_ids_empty_title(client):
    """测试跳过空标题"""
    client.search_movie_by_title = AsyncMock(return_value=None)
    client._initialized = True

    llm_items = [
        {"title": "", "score": 9.0, "reason": "推荐"},
        {"title": "Valid Movie", "score": 8.0, "reason": "推荐"},
    ]

    resolved = await client.resolve_llm_movie_ids(llm_items)

    # 空标题被跳过，只有有效电影被处理
    assert len(resolved) == 0  # search_movie_by_title 返回 None


@pytest.mark.asyncio
async def test_health_check_success(client):
    """测试健康检查成功"""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    result = await client.health_check()
    assert result is True


@pytest.mark.asyncio
async def test_health_check_failure(client):
    """测试健康检查失败"""
    mock_response = MagicMock()
    mock_response.status = 503
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    client._session = mock_session
    client._initialized = True

    result = await client.health_check()
    assert result is False


@pytest.mark.asyncio
async def test_update_user_profile_no_redis():
    """测试无 Redis 时更新用户偏好"""
    import sys
    module = sys.modules["services.integration.trad_rec_client"]
    original_redis = module.redis_client
    try:
        module.redis_client = None
        client = TraditionalRecommendationClient()
        result = await client.update_user_profile("user1", genre="action")
        assert result is False
    finally:
        module.redis_client = original_redis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
