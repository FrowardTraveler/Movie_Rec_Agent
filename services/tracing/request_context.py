"""
全链路追踪服务

使用 contextvars 实现 request_id 自动透传
通过包装 structlog 确保所有 logger 自动携带 request_id

使用方式：
    from services.tracing.request_context import set_request_id, get_request_id
    
    # API 入口设置 request_id
    set_request_id("abc-123-def")
    
    # 之后所有 logger.info() 自动携带 request_id 字段
"""

import uuid
import time
from typing import Optional

import contextvars

_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("span_id", default=None)


def generate_request_id() -> str:
    return f"req-{uuid.uuid4().hex[:12]}"


def generate_span_id() -> str:
    return f"span-{uuid.uuid4().hex[:8]}"


def set_request_id(request_id: str):
    _request_id.set(request_id)


def set_user_id(user_id: str):
    _user_id.set(user_id)


def set_span_id(span_id: str):
    _span_id.set(span_id)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def get_user_id() -> Optional[str]:
    return _user_id.get()


def get_span_id() -> Optional[str]:
    return _span_id.get()


def clear_context():
    _request_id.set(None)
    _user_id.set(None)
    _span_id.set(None)


def get_context_dict() -> dict:
    return {
        "request_id": _request_id.get(),
        "user_id": _user_id.get(),
        "span_id": _span_id.get(),
    }


class PerformanceTracker:
    def __init__(self):
        self._start_time = time.time()
        self._milestones: list = []
    
    def milestone(self, name: str):
        now = time.time()
        duration = round((now - self._start_time) * 1000, 2)
        self._milestones.append((name, now, duration))
        get_tracing_logger().info("milestone", name=name, duration_ms=duration)
    
    def get_summary(self) -> list:
        return [
            {"name": name, "duration_ms": duration}
            for name, _, duration in self._milestones
        ]
    
    def get_total_ms(self) -> float:
        return round((time.time() - self._start_time) * 1000, 2)


def _inject_context(kwargs: dict) -> dict:
    rid = _request_id.get()
    uid = _user_id.get()
    sid = _span_id.get()
    if rid:
        kwargs["request_id"] = rid
    if uid:
        kwargs["user_id"] = uid
    if sid:
        kwargs["span_id"] = sid
    return kwargs


import structlog as _structlog

_original_get_logger = _structlog.get_logger


class TracingLogger:
    def __init__(self, name: str = None):
        self._logger = _original_get_logger(name)
    
    def _log(self, method: str, event: str, **kwargs):
        kwargs = _inject_context(kwargs)
        getattr(self._logger, method)(event, **kwargs)
    
    def info(self, event: str, **kwargs):
        self._log("info", event, **kwargs)
    
    def debug(self, event: str, **kwargs):
        self._log("debug", event, **kwargs)
    
    def warning(self, event: str, **kwargs):
        self._log("warning", event, **kwargs)
    
    def warn(self, event: str, **kwargs):
        self._log("warning", event, **kwargs)
    
    def error(self, event: str, **kwargs):
        self._log("error", event, **kwargs)
    
    def exception(self, event: str, **kwargs):
        self._log("exception", event, **kwargs)


def get_tracing_logger(name: str = None) -> TracingLogger:
    return TracingLogger(name)


logger = TracingLogger()


def _patch_structlog_logger():
    _structlog.get_logger = lambda *a, **kw: TracingLogger(*a, **kw)


_patch_structlog_logger()
