"""
异步任务队列测试

测试 TaskQueue 的入队、注册处理器、Worker 消费循环
"""

import pytest
import asyncio

from services.queue.task_queue import TaskQueue


class MockRedis:
    """模拟 Redis 用于测试"""
    def __init__(self):
        self._streams = {}
        self._deleted = set()
    
    async def ping(self):
        return True
    
    async def xadd(self, stream_name, data):
        if stream_name not in self._streams:
            self._streams[stream_name] = []
        msg_id = f"{len(self._streams[stream_name])}-0"
        self._streams[stream_name].append((msg_id, data))
        return msg_id
    
    async def xread(self, streams, block=0, count=10):
        results = []
        for stream_name, last_id in streams.items():
            if stream_name in self._streams:
                messages = []
                start_from = False
                for msg_id, fields in self._streams[stream_name]:
                    if not start_from:
                        if msg_id == last_id or last_id == "0":
                            start_from = True
                            if last_id == "0" or msg_id != last_id:
                                messages.append((msg_id, fields))
                        continue
                    messages.append((msg_id, fields))
                if messages:
                    results.append((stream_name, messages))
        return results
    
    async def xdel(self, stream_name, msg_id):
        if stream_name in self._streams:
            self._streams[stream_name] = [
                (m_id, fields) for m_id, fields in self._streams[stream_name]
                if m_id != msg_id
            ]
    
    async def xlen(self, stream_name):
        if stream_name in self._streams:
            return len(self._streams[stream_name])
        return 0
    
    async def set(self, key, value):
        pass
    
    async def get(self, key):
        return None
    
    async def delete(self, key):
        pass


@pytest.fixture
async def task_queue():
    """创建测试用任务队列"""
    queue = TaskQueue()
    queue._redis = MockRedis()
    return queue


async def test_enqueue_task(task_queue):
    """测试任务入队"""
    result = await task_queue.enqueue(
        task_type="test_task",
        payload={"user_id": "test", "data": "value"}
    )
    assert result is True


async def test_enqueue_without_redis():
    """测试 Redis 未连接时入队"""
    queue = TaskQueue()
    queue._redis = None
    
    result = await queue.enqueue("test_task", {"data": "value"})
    assert result is False


async def test_register_handler(task_queue):
    """测试注册处理器"""
    async def test_handler(payload):
        return payload
    
    task_queue.register_handler("test_task", test_handler)
    assert "test_task" in task_queue._handlers


async def test_process_message(task_queue):
    """测试消息处理"""
    received = {}
    
    async def test_handler(payload):
        received.update(payload)
    
    task_queue.register_handler("test_task", test_handler)
    
    fields = {
        "type": "test_task",
        "payload": '{"user_id": "test", "value": "hello"}'
    }
    
    result = await task_queue._process_message(fields)
    assert result is True
    assert received.get("user_id") == "test"
    assert received.get("value") == "hello"


async def test_process_message_unknown_type(task_queue):
    """测试未知任务类型"""
    fields = {
        "type": "unknown_task",
        "payload": '{}'
    }
    
    result = await task_queue._process_message(fields)
    assert result is True


async def test_process_message_handler_error(task_queue):
    """测试处理器异常"""
    async def failing_handler(payload):
        raise RuntimeError("handler error")
    
    task_queue.register_handler("failing_task", failing_handler)
    
    fields = {
        "type": "failing_task",
        "payload": '{}'
    }
    
    result = await task_queue._process_message(fields)
    assert result is False


async def test_worker_loop(task_queue):
    """测试 Worker 消费循环"""
    processed = []
    
    async def test_handler(payload):
        processed.append(payload)
    
    task_queue.register_handler("test_task", test_handler)
    
    await task_queue.enqueue("test_task", {"user_id": "1"})
    await task_queue.enqueue("test_task", {"user_id": "2"})
    
    worker_task = asyncio.create_task(task_queue.start_worker())
    await asyncio.sleep(0.5)
    
    await task_queue.stop_worker()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    assert len(processed) >= 2


async def test_stop_worker(task_queue):
    """测试停止 Worker"""
    task_queue._running = True
    await task_queue.stop_worker()
    assert task_queue._running is False


async def test_double_start_worker(task_queue):
    """测试重复启动 Worker"""
    task_queue._running = True
    await task_queue.start_worker()
    # 应该直接返回，不报错


async def test_get_queue_stats(task_queue):
    """测试获取队列统计"""
    await task_queue.enqueue("test_task", {"data": "value"})
    
    stats = await task_queue.get_queue_stats()
    assert stats["queue_name"] == "task_queue"
    assert "pending_tasks" in stats
    assert "handlers" in stats


async def test_get_queue_stats_no_redis():
    """测试无 Redis 时获取统计"""
    queue = TaskQueue()
    queue._redis = None
    
    stats = await queue.get_queue_stats()
    assert "error" in stats


@pytest.mark.asyncio
async def test_retry_exhausted(task_queue):
    """测试重试次数耗尽"""
    msg_id = "test-1"
    fields = {
        "type": "test_task",
        "payload": '{}',
        "retries": "3",
    }
    
    await task_queue._handle_retry(msg_id, fields)
    
    # 超过最大重试次数，消息被删除
    length = await task_queue._redis.xlen(task_queue.QUEUE_NAME)
    assert length == 0


async def test_enqueue_with_priority(task_queue):
    """测试带优先级的任务入队"""
    result = await task_queue.enqueue(
        task_type="high_priority_task",
        payload={"data": "important"},
        priority=10
    )
    assert result is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
