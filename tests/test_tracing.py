"""
全链路追踪测试

测试 request_id 生成、上下文注入、PerformanceTracker
"""

import pytest
import time

from services.tracing.request_context import (
    generate_request_id,
    generate_span_id,
    set_request_id,
    set_user_id,
    set_span_id,
    get_request_id,
    get_user_id,
    get_span_id,
    get_context_dict,
    clear_context,
    PerformanceTracker,
    TracingLogger,
    get_tracing_logger,
    _inject_context,
)


def test_generate_request_id():
    """测试 request_id 生成"""
    request_id = generate_request_id()
    assert request_id.startswith("req-")
    assert len(request_id) == 16


def test_generate_span_id():
    """测试 span_id 生成"""
    span_id = generate_span_id()
    assert span_id.startswith("span-")
    assert len(span_id) == 13


def test_set_and_get_request_id():
    """测试设置和获取 request_id"""
    rid = "req-test-123"
    set_request_id(rid)
    assert get_request_id() == rid


def test_set_and_get_user_id():
    """测试设置和获取 user_id"""
    uid = "user-001"
    set_user_id(uid)
    assert get_user_id() == uid


def test_set_and_get_span_id():
    """测试设置和获取 span_id"""
    sid = "span-abc"
    set_span_id(sid)
    assert get_span_id() == sid


def test_get_context_dict():
    """测试获取完整上下文字典"""
    set_request_id("req-xyz")
    set_user_id("user-999")
    set_span_id("span-def")
    
    ctx = get_context_dict()
    assert ctx["request_id"] == "req-xyz"
    assert ctx["user_id"] == "user-999"
    assert ctx["span_id"] == "span-def"


def test_clear_context():
    """测试清空上下文"""
    set_request_id("req-clear")
    set_user_id("user-clear")
    set_span_id("span-clear")
    
    clear_context()
    
    assert get_request_id() is None
    assert get_user_id() is None
    assert get_span_id() is None


def test_inject_context():
    """测试上下文注入"""
    set_request_id("req-inject")
    set_user_id("user-inject")
    set_span_id("span-inject")
    
    kwargs = {"extra_field": "value"}
    result = _inject_context(kwargs)
    
    assert result["request_id"] == "req-inject"
    assert result["user_id"] == "user-inject"
    assert result["span_id"] == "span-inject"
    assert result["extra_field"] == "value"


def test_inject_context_partial():
    """测试部分上下文注入（只设置 request_id）"""
    clear_context()
    set_request_id("req-partial")
    
    kwargs = {}
    result = _inject_context(kwargs)
    
    assert result["request_id"] == "req-partial"
    assert "user_id" not in result
    assert "span_id" not in result


def test_tracing_logger_creation():
    """测试 TracingLogger 创建"""
    logger = TracingLogger("test-logger")
    assert logger is not None


def test_get_tracing_logger():
    """测试获取 TracingLogger 实例"""
    logger = get_tracing_logger()
    assert isinstance(logger, TracingLogger)


def test_get_tracing_logger_with_name():
    """测试带名称获取 TracingLogger"""
    logger = get_tracing_logger("custom-name")
    assert isinstance(logger, TracingLogger)


def test_tracing_logger_has_methods():
    """测试 TracingLogger 包含所有日志方法"""
    logger = TracingLogger()
    assert hasattr(logger, "info")
    assert hasattr(logger, "debug")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "warn")
    assert hasattr(logger, "error")
    assert hasattr(logger, "exception")


def test_performance_tracker_milestone():
    """测试 PerformanceTracker 里程碑记录"""
    tracker = PerformanceTracker()
    time.sleep(0.01)
    tracker.milestone("init")
    time.sleep(0.01)
    tracker.milestone("process")
    
    summary = tracker.get_summary()
    assert len(summary) == 2
    assert summary[0]["name"] == "init"
    assert summary[1]["name"] == "process"


def test_performance_tracker_get_total():
    """测试获取总耗时"""
    tracker = PerformanceTracker()
    time.sleep(0.01)
    
    total_ms = tracker.get_total_ms()
    assert total_ms > 0


def test_performance_tracker_milestone_duration():
    """测试里程碑耗时计算"""
    tracker = PerformanceTracker()
    time.sleep(0.05)
    tracker.milestone("slow_op")
    
    summary = tracker.get_summary()
    assert summary[0]["duration_ms"] > 0
    assert summary[0]["duration_ms"] >= 40


def test_multiple_request_ids_isolation():
    """测试多个请求 ID 的隔离"""
    set_request_id("req-first")
    first_id = get_request_id()
    
    set_request_id("req-second")
    second_id = get_request_id()
    
    assert first_id == "req-first"
    assert second_id == "req-second"


def test_context_default_values():
    """测试上下文默认值"""
    clear_context()
    
    assert get_request_id() is None
    assert get_user_id() is None
    assert get_span_id() is None


def test_request_id_format():
    """测试 request_id 格式"""
    for _ in range(10):
        rid = generate_request_id()
        assert rid.startswith("req-")
        # 长度应该是 16（"req-" + 12个hex字符）
        assert len(rid) == 16


def test_span_id_format():
    """测试 span_id 格式"""
    for _ in range(10):
        sid = generate_span_id()
        assert sid.startswith("span-")
        # 长度应该是 13（"span-" + 8个hex字符）
        assert len(sid) == 13


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
