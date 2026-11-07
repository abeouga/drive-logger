import pytest

from ct125_api.domain.data_file import DataFileName
from ct125_api.domain.exceptions import InvalidFileNameError


@pytest.mark.parametrize(
    ("raw", "media_type"),
    [
        ("rides.json", "application/json"),
        ("ride_ride_004.json", "application/json"),
        ("spec_ride_004.png", "image/png"),
        ("SPEC.PNG", "image/png"),
    ],
)
def test_accepts_data_file_names(raw, media_type):
    name = DataFileName.parse(raw)
    assert name.value == raw
    assert name.media_type == media_type


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "../secret.json",
        "raw/accel.csv",
        ".hidden.json",
        "rides.csv",
        "rides",
        "ride 1.json",
        "a" * 101 + ".json",
    ],
)
def test_rejects_unsafe_names(raw):
    with pytest.raises(InvalidFileNameError):
        DataFileName.parse(raw)
