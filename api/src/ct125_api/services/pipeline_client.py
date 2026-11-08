"""処理の Lambda（ct125-ride-pipeline）に頼む。公開用のバケットに書けるのは、その Lambda だけ。

台帳を書き換えた後（消す・戻す・公開する結果の切り替え）は {"action": "publish"}、
モデルの切り替えは {"action": "use_model", "version": ...} を、待たずに（非同期で）渡す。
"""

import json
from typing import Protocol


class PipelineClient(Protocol):
    def publish(self) -> None: ...
    def use_model(self, version: str) -> None: ...


class LambdaPipelineClient:
    def __init__(self, lambda_client, function_name: str) -> None:
        self._lambda = lambda_client
        self._function = function_name

    def publish(self) -> None:
        self._invoke({"action": "publish"})

    def use_model(self, version: str) -> None:
        self._invoke({"action": "use_model", "version": version})

    def _invoke(self, payload: dict) -> None:
        self._lambda.invoke(FunctionName=self._function, InvocationType="Event", Payload=json.dumps(payload).encode("utf-8"))
