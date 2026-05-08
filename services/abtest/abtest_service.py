"""
A/B 测试服务

支持对比不同推荐策略的效果（如：LLM推荐 vs 传统推荐）
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class ABTestConfig:
    """A/B 测试配置"""

    experiment_id: str
    name: str
    variants: Dict[str, float]  # variant_name -> weight (should sum to 1.0)
    start_time: float
    end_time: Optional[float] = None
    description: str = ""


class ABTestService:
    """
    A/B 测试服务

    功能：
    1. 管理实验配置
    2. 为用户分配实验变体
    3. 记录实验结果
    4. 提供实验效果统计
    """

    EXPERIMENT_KEY_PREFIX = "agent:abtest:"
    RESULT_KEY_PREFIX = "agent:abtest:result:"

    def __init__(self):
        self._redis_client = None
        self._experiments: Dict[str, ABTestConfig] = {}

    async def initialize(self, redis_client=None):
        """初始化"""
        self._redis_client = redis_client
        await self._load_experiments()

    async def _load_experiments(self):
        """加载默认实验配置"""
        # 默认实验：对比推荐策略
        default_experiment = ABTestConfig(
            experiment_id="recommend_strategy",
            name="推荐策略对比测试",
            variants={
                "llm_only": 0.5,  # 纯 LLM 推荐
                "traditional": 0.5,  # 传统推荐引擎
            },
            start_time=time.time(),
            description="对比 LLM 推荐和传统推荐的效果",
        )
        self._experiments["recommend_strategy"] = default_experiment

    def assign_variant(self, experiment_id: str, user_id: str) -> Optional[str]:
        """
        为用户分配实验变体

        Args:
            experiment_id: 实验 ID
            user_id: 用户 ID

        Returns:
            分配的变体名称，如果没有实验则返回 None
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        # 使用 user_id 的哈希值进行确定性分配
        hash_value = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        normalized = hash_value % 1000 / 1000.0  # 0-1 之间的值

        cumulative = 0.0
        for variant_name, weight in experiment.variants.items():
            cumulative += weight
            if normalized < cumulative:
                # 记录到 Prometheus
                try:
                    from services.metrics import record_ab_assignment

                    record_ab_assignment(experiment_id, variant_name)
                except Exception:
                    pass

                logger.info(
                    "A/B 测试分配变体",
                    experiment_id=experiment_id,
                    user_id=user_id,
                    variant=variant_name,
                )
                return variant_name

        # 兜底返回最后一个
        return list(experiment.variants.keys())[-1]

    async def record_result(
        self, experiment_id: str, user_id: str, variant: str, result: Dict[str, Any]
    ):
        """
        记录实验结果

        Args:
            experiment_id: 实验 ID
            user_id: 用户 ID
            variant: 变体名称
            result: 结果数据，包含：
                - clicked: 是否点击
                - rated: 评分
                - latency_ms: 延迟
        """
        try:
            import json

            result_data = {
                "user_id": user_id,
                "variant": variant,
                "timestamp": time.time(),
                **result,
            }

            key = f"{self.RESULT_KEY_PREFIX}{experiment_id}:{variant}"
            pipe = self._redis_client.pipeline()
            pipe.rpush(key, json.dumps(result_data, ensure_ascii=False))
            pipe.ltrim(key, -10000, -1)  # 保留最近 10000 条结果
            await pipe.execute()

            logger.debug("A/B 测试结果已记录", experiment_id=experiment_id, variant=variant)

        except Exception as e:
            logger.error("记录 A/B 测试结果失败", error=str(e))

    async def get_experiment_stats(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """
        获取实验统计结果

        Returns:
            各变体的统计数据
        """
        experiment = self._experiments.get(experiment_id)
        if not experiment:
            return None

        stats = {
            "experiment_id": experiment_id,
            "name": experiment.name,
            "variants": {},
        }

        for variant in experiment.variants.keys():
            key = f"{self.RESULT_KEY_PREFIX}{experiment_id}:{variant}"

            try:
                import json

                results_raw = await self._redis_client.lrange(key, 0, -1)
                results = [json.loads(r) for r in results_raw]

                if not results:
                    stats["variants"][variant] = {
                        "count": 0,
                        "avg_click_rate": 0,
                        "avg_rating": 0,
                        "avg_latency_ms": 0,
                    }
                    continue

                total = len(results)
                clicks = sum(1 for r in results if r.get("clicked", False))
                ratings = [r.get("rating", 0) for r in results if r.get("rating")]
                latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]

                stats["variants"][variant] = {
                    "count": total,
                    "avg_click_rate": round(clicks / total * 100, 2) if total > 0 else 0,
                    "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
                }

            except Exception as e:
                logger.error("获取 A/B 测试统计失败", variant=variant, error=str(e))
                stats["variants"][variant] = {
                    "count": 0,
                    "avg_click_rate": 0,
                    "avg_rating": 0,
                    "avg_latency_ms": 0,
                }

        return stats

    def get_all_experiments(self) -> List[Dict[str, Any]]:
        """获取所有实验列表"""
        return [
            {
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "variants": list(exp.variants.keys()),
                "description": exp.description,
            }
            for exp in self._experiments.values()
        ]


# 全局实例
ab_test_service = ABTestService()
