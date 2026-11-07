"""FastAPI アプリを組み立てる。

ローカル：uvicorn ct125_api.main:app --reload
Lambda ：lambda_handler.py が、このアプリを Mangum で包む
"""

from fastapi import FastAPI

from .errors import register_error_handlers
from .routers import data_router, health_router, me_router

API_PREFIX = "/api"


def create_app() -> FastAPI:
    app = FastAPI(
        title="CT125 走行データ API",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        redoc_url=None,
    )
    app.include_router(health_router.router, prefix=API_PREFIX)
    app.include_router(me_router.router, prefix=API_PREFIX)
    app.include_router(data_router.router, prefix=API_PREFIX)
    register_error_handlers(app)
    return app


app = create_app()
