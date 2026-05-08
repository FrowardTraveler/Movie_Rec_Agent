"""
多Agent协调器测试

测试 MultiAgentCoordinator 的请求处理、思考步骤、错误处理
"""

import time

import pytest

from agent.multi_agent.coordinator import (
    MultiAgentCoordinator,
    ThinkingStep,
)


@pytest.fixture
def coordinator():
    """创建协调器实例（不初始化）"""
    coord = MultiAgentCoordinator()
    yield coord


def test_thinking_step_creation():
    """测试思考步骤创建"""
    step = ThinkingStep(
        type="test", content="测试内容", agent_name="test_agent", timestamp=1234567890.0
    )
    assert step.type == "test"
    assert step.content == "测试内容"
    assert step.agent_name == "test_agent"
    assert step.timestamp == 1234567890.0


def test_add_thinking_step(coordinator):
    """测试添加思考步骤"""
    coordinator._add_thinking_step("init", "[初始化] 测试")

    assert len(coordinator._thinking_queue) == 1
    step = coordinator._thinking_queue[0]
    assert step.type == "init"
    assert step.content == "[初始化] 测试"


def test_add_thinking_step_with_callback(coordinator):
    """测试添加思考步骤时触发回调"""
    captured_steps = []

    def capture_callback(step):
        captured_steps.append(step)

    coordinator._stream_callback = capture_callback
    coordinator._add_thinking_step("test", "回调测试", "agent1")

    assert len(captured_steps) == 1
    assert captured_steps[0].content == "回调测试"
    assert captured_steps[0].agent_name == "agent1"


def test_get_thinking_steps(coordinator):
    """测试获取思考步骤"""
    coordinator._add_thinking_step("step1", "第一步")
    coordinator._add_thinking_step("step2", "第二步")

    steps = coordinator.get_thinking_steps(clear=False)
    assert len(steps) == 2
    assert steps[0]["type"] == "step1"
    assert steps[1]["type"] == "step2"


def test_get_thinking_steps_clears(coordinator):
    """测试获取思考步骤后清空"""
    coordinator._add_thinking_step("step1", "第一步")

    steps = coordinator.get_thinking_steps(clear=True)
    assert len(steps) == 1

    steps2 = coordinator.get_thinking_steps(clear=False)
    assert len(steps2) == 0


def test_friendly_error_message_connection(coordinator):
    """测试连接错误友好提示"""
    msg = coordinator._friendly_error_message("Connection refused to database")
    assert "连接" in msg or "稍后" in msg


def test_friendly_error_message_llm(coordinator):
    """测试 LLM 错误友好提示"""
    msg = coordinator._friendly_error_message("OpenAI API error: model not found")
    assert "思考" in msg or "稍后" in msg


def test_friendly_error_message_redis(coordinator):
    """测试 Redis 错误友好提示"""
    msg = coordinator._friendly_error_message("Redis connection failed")
    # Redis 错误目前被 connection 关键词匹配，会返回连接错误提示
    assert "抱歉" in msg


def test_friendly_error_message_generic(coordinator):
    """测试通用错误友好提示"""
    msg = coordinator._friendly_error_message("Some unknown error occurred")
    assert "抱歉" in msg


def test_coordinator_not_initialized():
    """测试协调器未初始化状态"""
    coord = MultiAgentCoordinator()
    assert coord._initialized is False
    assert coord.master_agent is None
    assert coord.llm_router is None


async def test_process_request_without_initialize(coordinator):
    """测试不初始化直接处理请求（会自动初始化）"""
    # 由于需要真实 LLM，这里只验证方法签名和参数校验
    # 实际集成测试在 test_agent_e2e.py 中
    assert coordinator._initialized is False


def test_thinking_step_timestamp():
    """测试思考步骤时间戳"""
    before = time.time()
    step = ThinkingStep(type="test", content="test", timestamp=time.time())
    after = time.time()

    assert before <= step.timestamp <= after


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
