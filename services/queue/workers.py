"""
后台任务 Worker

定义各类型任务的实际处理逻辑
"""

import structlog

from services.dialogue.dialogue_history import dialogue_history
from services.evaluation.online_metrics import online_metrics_service
from services.memory.memory_bank import memory_bank

logger = structlog.get_logger()


async def handle_save_dialogue(payload: dict):
    """保存对话历史"""
    user_id = payload["user_id"]
    user_input = payload["user_input"]
    agent_response = payload["agent_response"]
    intent = payload.get("intent", "multi_agent")
    skill_used = payload.get("skill_used", "multi_agent")

    await dialogue_history.add_turn(
        user_id=user_id,
        user_input=user_input,
        agent_response=agent_response,
        intent=intent,
        skill_used=skill_used,
    )
    logger.debug("对话历史已保存", user_id=user_id)


async def handle_save_recommendation(payload: dict):
    """保存推荐结果到记忆"""
    user_id = payload["user_id"]
    movies = payload["movies"]
    query = payload["query"]
    ttl = payload.get("ttl", 1800)

    await memory_bank.save_recommendation(user_id=user_id, movies=movies, query=query, ttl=ttl)
    logger.debug("推荐结果已保存到记忆", user_id=user_id, movie_count=len(movies))


async def handle_record_event(payload: dict):
    """记录用户行为事件"""
    user_id = payload["user_id"]
    event_type = payload["event_type"]
    movie_id = payload.get("movie_id")
    strategy = payload.get("strategy", "agent")
    query = payload.get("query", "")

    await online_metrics_service.record_event(
        user_id=user_id, event_type=event_type, movie_id=movie_id, strategy=strategy, query=query
    )
    logger.debug("事件已记录", user_id=user_id, event_type=event_type)


def get_default_handlers() -> dict:
    """获取默认任务处理器映射"""
    return {
        "save_dialogue": handle_save_dialogue,
        "save_recommendation": handle_save_recommendation,
        "record_event": handle_record_event,
    }
