"""
全局异常处理测试

测试自定义异常类、统一响应格式、各异常处理器行为
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exceptions import (
    AppError,
    BadRequestError,
    ErrorCode,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    _build_error_response,
    register_exception_handlers,
)


@pytest.fixture
def app():
    """创建测试用应用"""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/test/app-error")
    async def trigger_app_error():
        raise ForbiddenError("测试权限不足")

    @test_app.get("/test/not-found")
    async def trigger_not_found():
        raise NotFoundError("资源不存在")

    @test_app.get("/test/bad-request")
    async def trigger_bad_request():
        raise BadRequestError("参数错误")

    @test_app.get("/test/service-unavailable")
    async def trigger_service_unavailable():
        raise ServiceUnavailableError("服务不可用")

    @test_app.get("/test/unhandled")
    async def trigger_unhandled():
        raise RuntimeError("未处理的异常")

    @test_app.get("/test/http-exception")
    async def trigger_http_exception():
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="HTTP异常测试")

    @test_app.get("/test/validation")
    async def trigger_validation(value: int):
        return {"value": value}

    return test_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_build_error_response_basic():
    """测试基础错误响应构建"""
    result = _build_error_response(
        code="TEST_ERROR",
        message="测试错误",
        status_code=500,
    )
    assert result["success"] is False
    assert result["error"]["code"] == "TEST_ERROR"
    assert result["error"]["message"] == "测试错误"


def test_build_error_response_with_details():
    """测试带详情的错误响应"""
    result = _build_error_response(
        code="TEST_ERROR",
        message="测试错误",
        status_code=500,
        details={"key": "value"},
    )
    assert result["error"]["details"]["key"] == "value"


def test_build_error_response_with_request_id():
    """测试带 request_id 的错误响应"""
    result = _build_error_response(
        code="TEST_ERROR",
        message="测试错误",
        status_code=500,
        request_id="req-test-123",
    )
    assert result["error"]["request_id"] == "req-test-123"


def test_app_error_attributes():
    """测试 AppError 属性"""
    error = AppError(
        code=ErrorCode.FORBIDDEN,
        message="无权访问",
        status_code=403,
        details={"resource": "user"},
    )
    assert error.code == ErrorCode.FORBIDDEN
    assert error.message == "无权访问"
    assert error.status_code == 403
    assert error.details["resource"] == "user"


def test_forbidden_error_defaults():
    """测试 ForbiddenError 默认值"""
    error = ForbiddenError()
    assert error.code == ErrorCode.FORBIDDEN
    assert error.status_code == 403


def test_not_found_error_defaults():
    """测试 NotFoundError 默认值"""
    error = NotFoundError()
    assert error.code == ErrorCode.NOT_FOUND
    assert error.status_code == 404


def test_bad_request_error_defaults():
    """测试 BadRequestError 默认值"""
    error = BadRequestError()
    assert error.code == ErrorCode.BAD_REQUEST
    assert error.status_code == 400


def test_service_unavailable_error_defaults():
    """测试 ServiceUnavailableError 默认值"""
    error = ServiceUnavailableError()
    assert error.code == ErrorCode.SERVICE_UNAVAILABLE
    assert error.status_code == 503


def test_forbidden_error_handler(client):
    """测试 ForbiddenError 被正确捕获并转换"""
    response = client.get("/test/app-error")
    assert response.status_code == 403
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FORBIDDEN"
    assert body["error"]["message"] == "测试权限不足"


def test_not_found_handler(client):
    """测试 NotFoundError 被正确捕获并转换"""
    response = client.get("/test/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_bad_request_handler(client):
    """测试 BadRequestError 被正确捕获并转换"""
    response = client.get("/test/bad-request")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "BAD_REQUEST"


def test_service_unavailable_handler(client):
    """测试 ServiceUnavailableError 被正确捕获并转换"""
    response = client.get("/test/service-unavailable")
    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


def test_unhandled_exception_handler(client):
    """测试未处理异常返回统一格式"""
    response = client.get("/test/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "系统内部错误" in body["error"]["message"]


def test_http_exception_handler(client):
    """测试 HTTPException 被转换为统一格式"""
    response = client.get("/test/http-exception")
    assert response.status_code == 403
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FORBIDDEN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
