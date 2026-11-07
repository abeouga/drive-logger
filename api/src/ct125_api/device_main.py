"""デバイス API（機器からのアップロード）のアプリを組み立てる。

画面用のデータ API（main.py）とは別のアプリ・別の Lambda にする：
画面用は「S3 を読むだけ」、デバイス用は「raw/ に置くだけ」と、権限を分けるため。
"""

from fastapi import FastAPI

from .errors import register_error_handlers
from .main import API_PREFIX
from .routers import device_upload_router


def create_device_app() -> FastAPI:
    # 機器しか使わないので、説明書（/docs）は公開しない
    app = FastAPI(title="CT125 デバイス API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(device_upload_router.router, prefix=API_PREFIX)
    register_error_handlers(app)
    return app


app = create_device_app()
