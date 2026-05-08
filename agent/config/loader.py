"""
配置加载器

从 YAML 文件加载配置，并覆盖环境变量
"""

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigLoader:
    """
    配置加载器

    从 YAML 文件加载配置，支持环境变量覆盖
    """

    def __init__(self, config_path: str = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径，默认使用 configs/config.yaml
        """
        if config_path is None:
            # 自动查找配置文件
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "configs" / "config.yaml"

        self.config_path = Path(config_path)
        self._config = {}

    def load(self) -> dict:
        """
        加载配置文件

        Returns:
            配置字典
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        # 处理环境变量替换
        self._config = self._resolve_env_vars(self._config)

        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键，支持点号分隔的嵌套键，如 "llm.model"
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def _resolve_env_vars(self, obj: Any) -> Any:
        """
        递归解析配置中的环境变量

        Args:
            obj: 配置对象

        Returns:
            解析后的配置对象
        """
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            # 环境变量引用，如 ${OPENAI_API_KEY}
            env_var = obj[2:-1]
            return os.getenv(env_var, "")
        else:
            return obj
