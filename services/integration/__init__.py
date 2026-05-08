"""
集成服务模块

用于与外部系统（传统推荐系统、数据库等）交互
"""

from services.integration.trad_rec_client import (
    trad_rec_client,
    TraditionalRecommendationClient,
    RecommendationItem,
)

__all__ = ["trad_rec_client", "TraditionalRecommendationClient", "RecommendationItem"]
