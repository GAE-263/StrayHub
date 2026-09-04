from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    operation_id: UUID | None = None
    details: dict[str, object] = Field(default_factory=dict)


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": _request_id(request),
        },
    )


async def request_validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "請求資料格式錯誤",
            "request_id": _request_id(request),
        },
    )


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "code": "dependency_unavailable",
            "message": "資料服務暫時無法使用",
            "request_id": _request_id(request),
        },
    )


def _request_id(request: Request) -> str:
    server_request_id = getattr(request.state, "request_id", None)
    if isinstance(server_request_id, str) and server_request_id:
        return server_request_id
    return str(uuid4())
