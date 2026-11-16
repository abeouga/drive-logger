# -*- coding: utf-8 -*-
"""記録の設定（rides.json の recording）を meta.json と実測の fs から作る。"""
from ct125.processing import recording_settings

META_V37 = {"firmware": "CT125_LOGGER_V3.7", "accel": {"chip": "ADXL345", "bus": "i2c", "odr_hz": 800, "range_g": 16}}


def test_reads_meta_and_rounds_measured_rates():
    assert recording_settings(META_V37, 798.64, 399.32) == {
        "firmware": "CT125_LOGGER_V3.7",
        "accel_chip": "ADXL345",
        "accel_bus": "i2c",
        "accel_odr_hz": 800.0,
        "accel_fs_hz": 798.6,
        "accel_range_g": 16.0,
        "feature_fs_hz": 399.3,
    }


def test_bus_missing_before_v37_is_i2c():
    meta = {"firmware": "CT125_LOGGER_V3.6", "accel": {"chip": "ADXL345", "odr_hz": 800, "range_g": 16}}
    assert recording_settings(meta, 798.6, 399.3)["accel_bus"] == "i2c"


def test_spi_is_kept():
    meta = {"accel": {"bus": "spi", "odr_hz": 3200}}
    assert recording_settings(meta, 3190.0, 398.8)["accel_bus"] == "spi"


def test_broken_or_missing_values_become_none():
    meta = {"firmware": 37, "accel": {"chip": None, "bus": "uart", "odr_hz": "800", "range_g": True}}
    got = recording_settings(meta, 398.5, 398.5)
    assert got["firmware"] is None
    assert got["accel_chip"] is None
    assert got["accel_bus"] is None
    assert got["accel_odr_hz"] is None
    assert got["accel_range_g"] is None
    assert got["accel_fs_hz"] == 398.5


def test_meta_without_accel():
    got = recording_settings({}, 398.5, 398.5)
    assert got["accel_bus"] == "i2c" and got["accel_odr_hz"] is None and got["firmware"] is None
