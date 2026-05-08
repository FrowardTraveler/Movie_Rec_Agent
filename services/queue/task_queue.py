"""
异步任务队列服务

基于 Redis Streams 实现异步任务处理
主流程只负责入队，后台 Worker 负责消费，不阻塞用户请求
"""

import json
import time
import asyncio
from typing import Dict, Any, Optional, Callable

import redis.asyncio as aioredis
import structlog

from agent.config.agent_config import config

logger = structlog.get_logger()


class TaskQueue:
    """
    异步任务队列
    
    使用 Redis Streams 作为后端，支持：
    - 异步入队（不阻塞主流程）
    - 后台消费循环
    - 失败重试
    - 队列监控
    """
    
    QUEUE_NAME = "task_queue"
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # 秒
    
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._handlers: Dict[str, Callable] = {}
        self._running = False
    
    async def initialize(self):
        """初始化 Redis 连接"""
        try:
            self._redis = aioredis.from_url(
                config.redis.url,
                decode_responses=True
            )
            await self._redis.ping()
            logger.info("异步任务队列 Redis 连接成功")
        except Exception as e:
            logger.warning("异步任务队列 Redis 连接失败", error=str(e))
            self._redis = None
    
    def register_handler(self, task_type: str, handler: Callable):
        """注册任务处理器"""
        self._handlers[task_type] = handler
        logger.info("注册任务处理器", task_type=task_type)
    
    async def enqueue(self, task_type: str, payload: Dict[str, Any], priority: int = 0) -> bool:
        """
        异步入队（不阻塞）
        
        Args:
            task_type: 任务类型
            payload: 任务数据
            priority: 优先级（数值越大越优先）
            
        Returns:
            是否入队成功
        """
        if not self._redis:
            logger.warning("任务队列不可用，跳过入队", task_type=task_type)
            return False
        
        try:
            task_data = {
                "type": task_type,
                "payload": json.dumps(payload, ensure_ascii=False),
                "priority": str(priority),
                "timestamp": str(time.time()),
                "retries": "0",
            }
            
            await self._redis.xadd(self.QUEUE_NAME, task_data)
            logger.debug("任务已入队", task_type=task_type)
            return True
            
        except Exception as e:
            logger.error("任务入队失败", task_type=task_type, error=str(e))
            return False
    
    async def start_worker(self):
        """启动后台消费循环"""
        if self._running:
            return
        
        self._running = True
        logger.info("后台 Worker 已启动")
        
        # 使用 last_id 追踪已处理的消息
        last_id = "0"
        
        while self._running:
            try:
                # 阻塞读取新消息（最多等待 1 秒）
                messages = await self._redis.xread(
                    {self.QUEUE_NAME: last_id},
                    block=1000,
                    count=10
                )
                
                if not messages:
                    continue
                
                for stream, entries in messages:
                    for msg_id, fields in entries:
                        success = await self._process_message(fields)
                        
                        if success:
                            await self._redis.xdel(self.QUEUE_NAME, msg_id)
                            last_id = msg_id
                        else:
                            await self._handle_retry(msg_id, fields)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker 消费异常", error=str(e))
                await asyncio.sleep(1)
        
        logger.info("后台 Worker 已停止")
    
    async def stop_worker(self):
        """停止后台消费循环"""
        self._running = False
        logger.info("正在停止后台 Worker...")
    
    async def _process_message(self, fields: Dict[str, str]) -> bool:
        """处理单条消息"""
        task_type = fields.get("type")
        payload_str = fields.get("payload", "{}")
        
        if task_type not in self._handlers:
            logger.warning("未注册的任务处理器", task_type=task_type)
            return True
        
        try:
            payload = json.loads(payload_str)
            handler = self._handlers[task_type]
            await handler(payload)
            return True
        except Exception as e:
            logger.error("任务处理失败", task_type=task_type, error=str(e))
            return False
    
    async def _handle_retry(self, msg_id: str, fields: Dict[str, str]):
        """处理失败重试"""
        retries = int(fields.get("retries", 0))
        
        if retries >= self.MAX_RETRIES:
            await self._redis.xdel(self.QUEUE_NAME, msg_id)
            logger.warning("任务重试次数耗尽，丢弃", msg_id=msg_id)
            return
        
        fields["retries"] = str(retries + 1)
        fields["timestamp"] = str(time.time())
        
        await self._redis.xadd(self.QUEUE_NAME, fields)
        await self._redis.xdel(self.QUEUE_NAME, msg_id)
        
        await asyncio.sleep(self.RETRY_DELAY)
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        if not self._redis:
            return {"error": "Redis 未连接"}
        
        try:
            length = await self._redis.xlen(self.QUEUE_NAME)
            return {
                "queue_name": self.QUEUE_NAME,
                "pending_tasks": length,
                "handlers": list(self._handlers.keys()),
            }
        except Exception as e:
            return {"error": str(e)}


# 全局实例
task_queue = TaskQueue()
