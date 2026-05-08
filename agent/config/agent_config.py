"""
智能电影推荐 Agent - 配置模块

从 YAML 文件加载配置，支持环境变量覆盖
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _load_yaml_config() -> dict:
    """加载 YAML 配置文件并解析环境变量"""
    # 查找配置文件
    base_dir = Path(__file__).parent.parent.parent
    config_path = base_dir / "configs" / "config.yaml"

    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # 解析环境变量（支持 ${VAR:-default} 语法）
    def resolve_env_vars(obj):
        import re

        if isinstance(obj, dict):
            return {k: resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # 匹配 ${VAR:-default} 或 ${VAR}
            match = re.match(r"^\$\{([A-Za-z_]\w*)(?::-([^}]*))?\}$", obj)
            if match:
                env_var = match.group(1)
                default_val = match.group(2) if match.group(2) is not None else ""
                return os.getenv(env_var, default_val)
            return obj
        else:
            return obj

    return resolve_env_vars(cfg)


_yaml_config = _load_yaml_config()


@dataclass
class LLMConfig:
    """LLM 配置"""

    provider: str = _yaml_config.get("llm", {}).get("provider", "openai")
    model: str = _yaml_config.get("llm", {}).get("model", "gpt-4o-mini")
    temperature: float = _yaml_config.get("llm", {}).get("temperature", 0.3)
    max_tokens: int = _yaml_config.get("llm", {}).get("max_tokens", 1000)
    api_key: str = os.environ.get("OPENAI_API_KEY", "")
    base_url: str = os.environ.get("OPENAI_API_BASE", "")


@dataclass
class RedisConfig:
    """Redis 缓存配置"""

    host: str = _yaml_config.get("redis", {}).get("host", "localhost")
    port: int = _yaml_config.get("redis", {}).get("port", 6379)
    db: int = _yaml_config.get("redis", {}).get("db", 0)
    password: str = _yaml_config.get("redis", {}).get("password", "")
    cache_ttl: int = _yaml_config.get("redis", {}).get("cache_ttl", 300)

    @property
    def url(self) -> str:
        """生成 Redis URL"""
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class RecommendationConfig:
    """推荐引擎配置"""

    engine_path: str = _yaml_config.get("recommendation", {}).get(
        "engine_path", "../Movie_Rec_Agent/backend"
    )
    recall_top_k: int = _yaml_config.get("recommendation", {}).get("recall_top_k", 100)
    ranking_top_k: int = _yaml_config.get("recommendation", {}).get("ranking_top_k", 20)
    final_top_k: int = _yaml_config.get("recommendation", {}).get("final_top_k", 10)


@dataclass
class AgentConfig:
    """
    Agent 核心配置

    聚合所有子模块配置
    """

    app_name: str = _yaml_config.get("agent", {}).get("name", "MovieRecAgent")
    app_version: str = _yaml_config.get("agent", {}).get("version", "0.1.0")

    # 子配置
    llm: LLMConfig = field(default_factory=LLMConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    recommendation: RecommendationConfig = field(default_factory=RecommendationConfig)

    # 日志配置
    log_level: str = _yaml_config.get("logging", {}).get("level", "INFO")


# 全局配置实例
config = AgentConfig()
