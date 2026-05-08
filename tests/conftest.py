"""
测试配置

设置 Python 路径，使测试可以正确导入项目模块
"""

import sys
from pathlib import Path

# 将项目根目录添加到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio

import pytest


@pytest.fixture
def event_loop():
    """创建异步事件循环用于测试"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# 配置 pytest-asyncio 模式
def pytest_configure(config):
    """配置 pytest"""
    config.addinivalue_line("markers", "asyncio: mark test as async")
