"""Common Pydantic schemas — response wrappers, pagination, error models."""

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel[T]):
    data: list[T]
    metadata: dict


class ErrorDetail(BaseModel):
    code: str
    message: str
    trace_id: str | None = None


class ApiResponse(BaseModel[T]):
    data: T | None = None
    error: ErrorDetail | None = None
    metadata: dict | None = None


class MessageResponse(BaseModel):
    message: str
