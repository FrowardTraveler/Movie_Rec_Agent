"""
技能基类

定义所有 Skills 的统一接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseSkill(ABC):
    """
    技能基类

    所有 Skills 必须继承此类并实现 execute 方法
    """

    # 技能名称（唯一标识）
    name: str = "base_skill"

    # 技能描述（用于 Agent 理解）
    description: str = "基础技能"

    # 技能优先级（数字越小优先级越高）
    priority: int = 99

    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行技能

        Args:
            **kwargs: 技能参数

        Returns:
            执行结果字典
        """
        return await self._execute(**kwargs)

    @abstractmethod
    async def _execute(self, **kwargs) -> Dict[str, Any]:
        """
        子类必须实现的执行方法

        Args:
            **kwargs: 技能参数

        Returns:
            执行结果字典
        """
        pass
