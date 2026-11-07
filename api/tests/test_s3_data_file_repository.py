import io

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from ct125_api.domain.data_file import DataFileName
from ct125_api.domain.dataset import SHARED_DATASET
from ct125_api.domain.exceptions import DataFileNotFoundError
from ct125_api.repositories.s3_data_file_repository import S3DataFileRepository


@pytest.fixture
def s3():
    client = boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stubber:
        yield client, stubber


def test_reads_from_dataset_folder(s3):
    client, stubber = s3
    body = b'{"rides": []}'
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(body), len(body))},
        {"Bucket": "bucket", "Key": "app/v1/datasets/shared/rides.json"},
    )
    repository = S3DataFileRepository(client, "bucket", "app/v1/datasets/")

    data_file = repository.read(SHARED_DATASET, DataFileName.parse("rides.json"))

    assert data_file.content == body


def test_missing_key_becomes_not_found(s3):
    client, stubber = s3
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    repository = S3DataFileRepository(client, "bucket", "app/v1/datasets/")

    with pytest.raises(DataFileNotFoundError):
        repository.read(SHARED_DATASET, DataFileName.parse("rides.json"))
