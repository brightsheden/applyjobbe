from ninja import Schema,ModelSchema
from typing import Optional, Any,List,Generic,TypeVar
from datetime import date, datetime
from pydantic import BaseModel

T = TypeVar("T")

class BaseResponseSchema(Schema):
    success: bool = True
    data: Optional[Any] = None
    message: Optional[str] = None


class ErrorResponse(Schema):
    message: str = "An error occurred"
    success:bool = False
    detail: str | None = None
    code: int = 500


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool