"""S3 からデータファイルを読む。

置き場所：s3://<bucket>/<prefix><データセット>/<ファイル名>
例：s3://ct125-logger-xxxx/app/v1/datasets/shared/rides.json
"""

from botocore.exceptions import ClientError

from ..domain.data_file import DataFile, DataFileName
from ..domain.dataset import DatasetId
from ..domain.exceptions import DataFileNotFoundError

NOT_FOUND_CODES = {"NoSuchKey", "404"}


class S3DataFileRepository:
    def __init__(self, s3_client, bucket: str, prefix: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix

    def read(self, dataset: DatasetId, name: DataFileName) -> DataFile:
        key = self._key_for(dataset, name)
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _is_not_found(error):
                raise DataFileNotFoundError(f"{name.value} がありません") from error
            raise
        content = response["Body"].read()
        return DataFile(name=name, content=content)

    def _key_for(self, dataset: DatasetId, name: DataFileName) -> str:
        return f"{self._prefix}{dataset.value}/{name.value}"


def _is_not_found(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code", "")
    return code in NOT_FOUND_CODES
