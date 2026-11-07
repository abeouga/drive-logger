"""Lambda の入口。API Gateway（HTTP API）のイベントを、Mangum が FastAPI のリクエストに変える。

Lambda の設定：ハンドラー = ct125_api.lambda_handler.handler
"""

from mangum import Mangum

from .main import app

handler = Mangum(app, lifespan="off")
