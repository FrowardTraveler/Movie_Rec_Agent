"""
熔断器测试

测试 CircuitBreaker 的三种状态转换、重试机制、熔断保护
"""

import asyncio

import pytest

from services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    _is_retryable,
)


@pytest.fixture
def breaker():
    """创建测试用熔断器（低阈值加速测试）"""
    return CircuitBreaker(
        name="test-service",
        failure_threshold=3,
        recovery_timeout=1,
        success_threshold=1,
        retry_attempts=1,
    )


async def test_normal_call(breaker):
    """测试正常调用"""

    async def success_func():
        return "ok"

    result = await breaker.call(success_func)
    assert result == "ok"
    assert breaker.state == CircuitState.CLOSED


async def test_failure_triggers_circuit(breaker):
    """测试连续失败触发熔断"""

    async def failing_func():
        raise ValueError("service down")

    for _ in range(3):
        try:
            await breaker.call(failing_func)
        except ValueError:
            pass

    assert breaker.state == CircuitState.OPEN
    assert breaker._failure_count >= 3


async def test_open_state_rejects_calls(breaker):
    """测试熔断状态拒绝请求"""

    async def failing_func():
        raise ValueError("service down")

    for _ in range(3):
        try:
            await breaker.call(failing_func)
        except ValueError:
            pass

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(failing_func)


async def test_half_open_recovery(breaker):
    """测试半开状态自动恢复"""

    async def failing_func():
        raise ValueError("service down")

    async def success_func():
        return "recovered"

    for _ in range(3):
        try:
            await breaker.call(failing_func)
        except ValueError:
            pass

    assert breaker.state == CircuitState.OPEN

    await asyncio.sleep(1.1)

    result = await breaker.call(success_func)
    assert result == "recovered"
    assert breaker.state == CircuitState.CLOSED


async def test_half_open_failed_again(breaker):
    """测试半开状态试探失败后继续熔断"""

    async def failing_func():
        raise ValueError("service down")

    for _ in range(3):
        try:
            await breaker.call(failing_func)
        except ValueError:
            pass

    await asyncio.sleep(1.1)

    try:
        await breaker.call(failing_func)
    except ValueError:
        pass

    assert breaker.state == CircuitState.OPEN


def test_remaining_seconds(breaker):
    """测试剩余时间计算"""

    async def failing_func():
        raise ValueError("service down")

    async def run():
        for _ in range(3):
            try:
                await breaker.call(failing_func)
            except ValueError:
                pass

        remaining = breaker.remaining_seconds
        assert remaining > 0
        assert remaining <= breaker.recovery_timeout

    asyncio.get_event_loop().run_until_complete(run())


async def test_manual_reset(breaker):
    """测试手动重置熔断器"""

    async def failing_func():
        raise ValueError("service down")

    for _ in range(3):
        try:
            await breaker.call(failing_func)
        except ValueError:
            pass

    assert breaker.state == CircuitState.OPEN

    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker._failure_count == 0


async def test_get_stats(breaker):
    """测试获取熔断器状态"""

    async def success_func():
        return "ok"

    await breaker.call(success_func)
    stats = breaker.get_stats()

    assert stats["name"] == "test-service"
    assert stats["state"] == "closed"
    assert stats["failure_count"] == 0
    assert stats["failure_threshold"] == 3


def test_retryable_exceptions():
    """测试可重试异常判断"""
    assert _is_retryable(ValueError()) is True
    assert _is_retryable(RuntimeError()) is True

    assert _is_retryable(asyncio.TimeoutError()) is False
    assert _is_retryable(asyncio.CancelledError()) is False
    assert _is_retryable(KeyboardInterrupt()) is False


async def test_call_sync(breaker):
    """测试同步函数调用"""

    def success_func():
        return "sync-ok"

    result = breaker.call_sync(success_func)
    assert result == "sync-ok"


async def test_call_sync_failure(breaker):
    """测试同步函数失败"""

    def failing_func():
        raise RuntimeError("sync-error")

    with pytest.raises(RuntimeError):
        breaker.call_sync(failing_func)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
