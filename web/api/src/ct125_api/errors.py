"""業務上の失敗（domain/exceptions.py）を HTTP の応答に変える。

ルーターやサービスは HTTP のステータスを知らなくてよい。対応表はこのファイルだけにある。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .domain.exceptions import (
    DataFileNotFoundError,
    DomainError,
    InvalidFileNameError,
    NotAuthenticatedError,
)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    InvalidFileNameError: 400,
    NotAuthenticatedError: 401,
    DataFileNotFoundError: 404,
}


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)


async def _handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
    status = _status_for(error)
    return JSONResponse(status_code=status, content={"detail": str(error)})


def _status_for(error: DomainError) -> int:
    for error_type, status in STATUS_BY_ERROR.items():
        if isinstance(error, error_type):
            return status
    return 500
