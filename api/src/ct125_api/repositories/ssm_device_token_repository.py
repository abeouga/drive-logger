"""機器のトークンのハッシュを SSM パラメーターストアから読む。

置き場所：<prefix><機器ID>/token-sha256（例：/ct125/devices/d01/token-sha256）
登録と無効化は ct125-logger の `python -m ct125 register-device` / `revoke-device`。
"""

from botocore.exceptions import ClientError

PARAMETER_NOT_FOUND = "ParameterNotFound"


class SsmDeviceTokenRepository:
    def __init__(self, ssm_client, prefix: str) -> None:
        self._ssm = ssm_client
        self._prefix = prefix

    def token_hash(self, device_id: str) -> str | None:
        try:
            response = self._ssm.get_parameter(Name=self._name_for(device_id), WithDecryption=True)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == PARAMETER_NOT_FOUND:
                return None
            raise
        return response["Parameter"]["Value"]

    def _name_for(self, device_id: str) -> str:
        return f"{self._prefix}{device_id}/token-sha256"
