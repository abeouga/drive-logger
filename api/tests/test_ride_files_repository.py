"""完全に削除（#82）で S3 のファイルを消す部品。消す範囲が、その走行のフォルダーだけであることを確かめる。"""

import boto3
import pytest
from botocore.stub import Stubber

from ct125_api.repositories.ride_files_repository import RideFilesDeleteError, S3RideFilesRepository


@pytest.fixture
def s3():
    client = boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stubber:
        yield client, stubber


def repository(client):
    return S3RideFilesRepository(client, "raw-bucket", "", "work-bucket", "")


def _objects(keys):
    return {"Objects": [{"Key": key} for key in keys], "Quiet": True}


def test_deletes_only_the_ride_folder_in_raw(s3):
    client, stubber = s3
    keys = ["ride_20261109_010000/accel.csv", "ride_20261109_010000/meta.json"]
    stubber.add_response("list_objects_v2", {"Contents": [{"Key": k} for k in keys], "IsTruncated": False},
                         {"Bucket": "raw-bucket", "Prefix": "ride_20261109_010000/"})
    stubber.add_response("delete_objects", {"Deleted": [{"Key": k} for k in keys]}, {"Bucket": "raw-bucket", "Delete": _objects(keys)})

    assert repository(client).delete_raw("ride_20261109_010000") == 2
    stubber.assert_no_pending_responses()


def test_deletes_only_the_ride_results_of_the_run(s3):
    client, stubber = s3
    prefix = "runs/20261109T020000Z-aaaaaa/rides/ride_20261109_010000/"
    stubber.add_response("list_objects_v2", {"Contents": [{"Key": prefix + "summary.json"}], "IsTruncated": False},
                         {"Bucket": "work-bucket", "Prefix": prefix})
    stubber.add_response("delete_objects", {}, {"Bucket": "work-bucket", "Delete": _objects([prefix + "summary.json"])})

    assert repository(client).delete_results("20261109T020000Z-aaaaaa", "ride_20261109_010000") == 1
    stubber.assert_no_pending_responses()


def test_nothing_to_delete_calls_no_delete(s3):
    client, stubber = s3
    stubber.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": "raw-bucket", "Prefix": "ride_001/"})

    assert repository(client).delete_raw("ride_001") == 0


def test_partial_failure_is_raised(s3):
    client, stubber = s3
    stubber.add_response("list_objects_v2", {"Contents": [{"Key": "ride_001/a.csv"}], "IsTruncated": False},
                         {"Bucket": "raw-bucket", "Prefix": "ride_001/"})
    stubber.add_response("delete_objects", {"Errors": [{"Key": "ride_001/a.csv", "Code": "AccessDenied"}]},
                         {"Bucket": "raw-bucket", "Delete": _objects(["ride_001/a.csv"])})

    with pytest.raises(RideFilesDeleteError, match="AccessDenied"):
        repository(client).delete_raw("ride_001")
