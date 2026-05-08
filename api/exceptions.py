"""
全局异常处理

统一所有 API 的错误响应格式
"""

from typing import Optional, Any, Dict
from enum import Enum

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

import structlog
from services.tracing.request_context import get_request_id

logger = structlog.get_logger()


class ErrorCode(str, Enum):
    """错误码枚举"""
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    BAD_REQUEST = "BAD_REQUEST"


class AppError(Exception):
    """应用自定义异常基类"""
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ForbiddenError(AppError):
    """权限不足"""
    def __init__(self, message: str = "无权执行此操作", details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.FORBIDDEN,
            message=message,
            status_code=403,
            details=details,
        )


class NotFoundError(AppError):
    """资源不存在"""
    def __init__(self, message: str = "资源不存在", details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=404,
            details=details,
        )


class BadRequestError(AppError):
    """请求参数错误"""
    def __init__(self, message: str = "请求参数错误", details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.BAD_REQUEST,
            message=message,
            status_code=400,
            details=details,
        )


class ServiceUnavailableError(AppError):
    """服务不可用"""
    def __init__(self, message: str = "服务暂时不可用", details: Optional[Dict] = None):
        super().__init__(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=message,
            status_code=503,
            details=details,
        )


def _build_error_response(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict] = None,
    request_id: Optional[str] = None,
) -> Dict:
    """构建统一错误响应体"""
    error_detail: Dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if details:
        error_detail["details"] = details
    if request_id:
        error_detail["request_id"] = request_id
    
    return {
        "success": False,
        "error": error_detail,
    }


def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """处理应用自定义异常"""
        rid = get_request_id()
        logger.warning(
            "业务异常",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=rid,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_response(
                code=exc.code.value if isinstance(exc.code, ErrorCode) else exc.code,
                message=exc.message,
                status_code=exc.status_code,
                details=exc.details,
                request_id=rid,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """处理 FastAPI HTTPException，统一格式"""
        rid = get_request_id()
        logger.warning(
            "HTTP 异常",
            status_code=exc.status_code,
            detail=exc.detail,
            request_id=rid,
        )
        
        code_map = {
            400: ErrorCode.BAD_REQUEST,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            429: ErrorCode.RATE_LIMITED,
            500: ErrorCode.INTERNAL_ERROR,
            503: ErrorCode.SERVICE_UNAVAILABLE,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_response(
                code=code.value,
                message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                status_code=exc.status_code,
                request_id=rid,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """处理请求参数校验错误"""
        rid = get_request_id()
        errors = exc.errors()
        
        error_messages = []
        for err in errors:
            field = ".".join(str(loc) for loc in err.get("loc", []))
            msg = err.get("msg", "")
            error_messages.append(f"{field}: {msg}")
        
        message = "; ".join(error_messages) if error_messages else "参数校验失败"
        
        logger.warning(
            "参数校验失败",
            errors=errors,
            request_id=rid,
        )
        
        return JSONResponse(
            status_code=400,
            content=_build_error_response(
                code=ErrorCode.VALIDATION_ERROR.value,
                message=message,
                status_code=400,
                details={"raw_errors": errors},
                request_id=rid,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """处理所有未捕获的异常"""
        rid = get_request_id()
        logger.error(
            "未处理异常",
            error=str(exc),
            exc_info=True,
            request_id=rid,
        )
        
        return JSONResponse(
            status_code=500,
            content=_build_error_response(
                code=ErrorCode.INTERNAL_ERROR.value,
                message="系统内部错误，请稍后重试",
                status_code=500,
                request_id=rid,
            ),
        )
