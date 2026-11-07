# -*- coding: utf-8 -*-
"""機器登録（ct125/devices.py）のテスト。SSM には繋がない。"""
import hashlib

import boto3
import pytest
from botocore.stub import ANY, Stubber

from ct125 import devices


def _ssm():
    return boto3.client("ssm", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")


def test_register_stores_only_the_hash():
    ssm = _ssm()
    with Stubber(ssm) as stubber:
        stubber.add_response(
            "put_parameter",
            {"Version": 1},
            {"Name": "/ct125/devices/d01/token-sha256", "Value": ANY, "Type": "SecureString", "Overwrite": False, "Description": ANY},
        )
        token = devices.register(ssm, "d01")
    assert len(token) >= 40
    assert devices.hash_token(token) == hashlib.sha256(token.encode()).hexdigest()


def test_register_twice_needs_rotate():
    ssm = _ssm()
    with Stubber(ssm) as stubber:
        stubber.add_client_error("put_parameter", service_error_code="ParameterAlreadyExists", http_status_code=400)
        with pytest.raises(devices.DeviceAlreadyRegisteredError):
            devices.register(ssm, "d01")


@pytest.mark.parametrize("device_id", ["D01", "", "d01/../x", "a" * 33])
def test_rejects_bad_device_ids(device_id):
    with pytest.raises(ValueError):
        devices.register(_ssm(), device_id)


def test_hash_matches_the_api_side():
    # データ API（D:/ct125-app/api の device_authenticator.hash_token）と同じ作り方であること
    assert devices.hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
