"""
熔断器模式实现

保护系统免受级联故障，当外部服务连续失败时自动切断请求
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


class CircuitState(Enum):
    """熔断器状态"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """熔断器打开异常"""

    def __init__(self, service_name: str, remaining_seconds: float = 0):
        self.service_name = service_name
        self.remaining_seconds = remaining_seconds
        super().__init__(f"服务 '{service_name}' 已熔断，{remaining_seconds:.0f}秒后重试")


def _is_retryable(exc: BaseException) -> bool:
    """
    判断异常是否可重试

    超时、取消错误不重试（避免浪费更多时间）
    仅对网络抖动、连接错误等瞬时故障重试
    """
    if isinstance(exc, (asyncio.TimeoutError, asyncio.CancelledError, KeyboardInterrupt)):
        return False

    error_str = str(exc).lower()
    if "timeout" in error_str or "cancelled" in error_str:
        return False

    return True


class CircuitBreaker:
    """
    熔断器

    工作原理：
    1. 正常状态（CLOSED）：请求正常通过，记录失败次数
    2. 失败次数达到阈值 -> 进入熔断状态（OPEN），拒绝所有请求
    3. 等待恢复时间后 -> 进入半开状态（HALF_OPEN），允许试探性请求
    4. 试探成功 -> 恢复正常（CLOSED）；试探失败 -> 继续熔断（OPEN）

    示例：
        breaker = CircuitBreaker(
            name="LLM服务",
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=2
        )

        try:
            result = await breaker.call(llm.ainvoke, messages)
        except CircuitBreakerOpenError:
            result = fallback_result
    """

    def __init__(
        self,
        name: str = "unknown",
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        retry_attempts: int = 2,
        retry_min_wait: float = 0.5,
        retry_max_wait: float = 5.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_state_change_time = time.time()

        self._retry_decorator = retry(
            stop=stop_after_attempt(retry_attempts),
            wait=wait_exponential(multiplier=1, min=retry_min_wait, max=retry_max_wait),
            retry=retry_if_exception(_is_retryable),
            before_sleep=before_sleep_log(logger, logging.WARNING, exc_info=True),
            reraise=True,
        )

    def _retry_async_func(self, func: Callable, *args, **kwargs) -> Any:
        """包装异步函数进行重试"""

        @self._retry_decorator
        async def _retry_wrapper():
            return await func(*args, **kwargs)

        return _retry_wrapper()

    @property
    def state(self) -> CircuitState:
        """获取当前状态，并自动处理状态转换"""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                self._last_state_change_time = time.time()
                logger.info(f"[{self.name}] 熔断器进入半开状态，开始试探")
        return self._state

    @property
    def remaining_seconds(self) -> float:
        """距离下次试探的剩余秒数"""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self._last_failure_time
        return max(0.0, self.recovery_timeout - elapsed)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """通过熔断器调用异步函数"""
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = self.remaining_seconds
            logger.warning(f"[{self.name}] 熔断器打开，拒绝请求", remaining_seconds=remaining)
            raise CircuitBreakerOpenError(self.name, remaining)

        try:
            result = await self._retry_async_func(func, *args, **kwargs)
            self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception:
            self._on_failure()
            raise

    def call_sync(self, func: Callable, *args, **kwargs) -> Any:
        """通过熔断器调用同步函数"""
        current_state = self.state

        if current_state == CircuitState.OPEN:
            remaining = self.remaining_seconds
            logger.warning(f"[{self.name}] 熔断器打开，拒绝请求", remaining_seconds=remaining)
            raise CircuitBreakerOpenError(self.name, remaining)

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitBreakerOpenError:
            raise
        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        """请求成功时的处理"""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._last_state_change_time = time.time()
                logger.info(f"[{self.name}] 熔断器恢复正常")
        else:
            self._failure_count = 0

    def _on_failure(self):
        """请求失败时的处理"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._last_state_change_time = time.time()
            logger.warning(f"[{self.name}] 试探失败，继续熔断")
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._last_state_change_time = time.time()
            logger.warning(
                f"[{self.name}] 失败次数达到阈值({self._failure_count}/{self.failure_threshold})，触发熔断",
                recovery_timeout=self.recovery_timeout,
            )

    def reset(self):
        """手动重置熔断器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_state_change_time = time.time()
        logger.info(f"[{self.name}] 熔断器已手动重置")

    def get_stats(self) -> dict:
        """获取熔断器状态统计"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "remaining_seconds": self.remaining_seconds,
        }
