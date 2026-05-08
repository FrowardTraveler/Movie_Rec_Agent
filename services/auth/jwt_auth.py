"""
JWT 认证模块

复用传统推荐系统的 JWT secret_key 进行无状态认证
不依赖数据库，只验证 token 签名和有效期
"""

import os
from dataclasses import dataclass
from typing import Optional

import structlog
from jose import ExpiredSignatureError, JWTError, jwt

logger = structlog.get_logger()


def _is_auth_enabled() -> bool:
    """检查认证是否启用"""
    enabled = os.getenv("AUTH_ENABLED", "").lower()
    return enabled in ("true", "1", "yes", "on")


def _get_secret_key() -> str:
    """获取 JWT secret_key"""
    return os.getenv("JWT_SECRET_KEY", "")


@dataclass
class AuthUser:
    """认证用户信息"""

    user_id: int
    username: str = ""


def verify_token(token: str) -> Optional[AuthUser]:
    """
    验证 JWT token，返回用户信息

    复用传统推荐系统的 secret_key，实现跨系统认证
    """
    if not _is_auth_enabled():
        return None

    secret_key = _get_secret_key()
    if not secret_key:
        return None

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])

        user_id_str = payload.get("sub")
        if user_id_str is None:
            return None

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None

        return AuthUser(
            user_id=user_id,
            username=payload.get("username", ""),
        )

    except ExpiredSignatureError:
        logger.warning("JWT token 已过期")
        return None
    except JWTError as e:
        logger.warning("JWT token 验证失败", error=str(e))
        return None
    except Exception as e:
        logger.error("JWT token 验证异常", error=str(e))
        return None
