"""デバイス API の Lambda の入口（ハンドラー = ct125_api.device_lambda_handler.handler）。"""

from mangum import Mangum

from .device_main import app

handler = Mangum(app, lifespan="off")
