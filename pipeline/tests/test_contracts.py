# -*- coding: utf-8 -*-
"""pipeline の読み込み・書き出しが、フォルダーをまたぐ約束（リポジトリの contracts/）と合っているかを確かめる。

画面用 JSON の見本（contracts/examples/app/）は、ここで本物の書き出しの関数から作り直して一致を確かめる。
書き出しを変えて見本を作り直すとき：CT125_WRITE_CONTRACT_EXAMPLES=1 を付けてこのテストを流す。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ct125 import devices, export, flow, io, processing, records
from ct125.cloud import commands

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
EXAMPLES = CONTRACTS / "examples" / "app"


def load(relative: str) -> dict:
    return json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))


def validator(relative: str) -> Draft202012Validator:
    resources = []
    for path in CONTRACTS.glob("*/*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Draft202012Validator(load(relative), registry=Registry().with_resources(resources), format_checker=FormatChecker())


def table_fields(name: str) -> list[str]:
    return [field["name"] for field in load(f"sd/{name}.table.json")["fields"]]


# ------------------------------------------------------------------ SD の記録の読み込み（io.py）
def test_csv_columns_match_tables():
    assert io.ACCEL_COLS == table_fields("accel")
    assert io.GPS_COLS == table_fields("gps")
    assert io.EVENT_COLS == table_fields("events")


def test_required_and_memo_files_match_session():
    session = load("sd/session.json")
    assert set(io.REQUIRED_FILES) == {item["name"] for item in session["files"] if item["required"]}
    assert list(io.MEMO_FILES) == session["memo_files"]


def test_load_ride_needs_the_required_files(tmp_path):
    ride = tmp_path / "ride_001"
    ride.mkdir()
    (ride / "accel.csv").write_text("n,t_us,ax_g,ay_g,az_g\n0,0,0,0,1\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="gps.csv, meta.json"):
        io.load_ride("ride_001", tmp_path)


def test_read_memo_prefers_notes_md(tmp_path):
    (tmp_path / "memo.txt").write_text("古いメモ", encoding="utf-8")
    assert io.read_memo(tmp_path) == "古いメモ"
    (tmp_path / "notes.md").write_text("# 新しいメモ\n", encoding="utf-8")
    assert io.read_memo(tmp_path) == "# 新しいメモ 古いメモ"


# ------------------------------------------------------------------ 送信の手順
def test_marker_name_matches_upload_contract():
    assert flow.UPLOAD_COMPLETE == load("upload/upload.json")["raw_files"]["complete"]["name"]


def test_pc_upload_sends_only_allowed_files():
    from ct125 import device_upload

    assert device_upload.SEND_FILES == load("upload/upload.json")["files"]["allowed"]


def test_ledger_entry_reads_the_upload_marker():
    example = load("examples/upload/upload_complete.json")
    entry = records.new_entry(example["ride_id"], example)
    assert (entry["device_id"], entry["local_session"], entry["source"]) == ("d01", "ride_013", "device")
    legacy = {"ride_id": "ride_004", "files": ["accel.csv"], "uploaded_at": "2026-11-07T14:35:07.208985+00:00"}  # PC から直接上げた古い印
    validator("upload/upload_complete.schema.json").validate(legacy)
    assert records.new_entry("ride_004", legacy)["source"] == "legacy"
    assert records.new_entry("ride_004", None)["received_at"] is None


@pytest.mark.parametrize("ride_id", ["ride_20261108_011304", "ride_20261108_011304_2", "ride_004", "ride_1", "ride_0001", "x", "../ride_004", "ride_20261108"])
def test_ride_id_pattern_matches_common(ride_id):
    common = load("common.json")["ride_id"]
    expected = bool(re.fullmatch(common["pattern"], ride_id) or re.fullmatch(common["legacy_pattern"], ride_id))
    assert bool(commands.RIDE_ID_PATTERN.fullmatch(ride_id)) == expected


def test_device_id_pattern_matches_common():
    assert "^" + devices.DEVICE_ID_PATTERN.pattern + "$" == load("common.json")["device_id"]["pattern"]


def test_stop_speed_matches_common():
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "default.yaml").read_text(encoding="utf-8"))
    assert cfg["stop_speed_kmh"] == load("common.json")["stop_speed_kmh"]["value"]


# ------------------------------------------------------------------ 画面用 JSON（export.py）
FIXED_GENERATED_AT_MS = 1762650000000  # 見本の rides.json の作った時刻（毎回同じにする）
EXAMPLE_MODEL_VERSION = "20261108-180231"  # 見本の判定に使ったモデルの版


def _windows(n: int = 12, gps: bool = True) -> pd.DataFrame:
    """書き出しの見本にする小さな走行。gps=True なら先頭 2 窓だけ GPS が無い。"""
    t_rel = np.arange(n) + 0.5
    df = pd.DataFrame({
        "ride_id": "ride_20261108_011304" if gps else "ride_007",
        "win": np.arange(n), "t_start": np.arange(n, dtype=float), "t_rel": t_rel,
        "t_abs": pd.date_range("2026-11-02 14:00:00.5", periods=n, freq="s", tz="Asia/Tokyo") if gps else pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, Asia/Tokyo]"),
        "lat": 35.0 + np.arange(n) * 0.0001 if gps else np.nan, "lon": 135.0 + np.arange(n) * 0.0001 if gps else np.nan,
        "has_gps": (np.arange(n) >= 2) if gps else False,
        "speed_kmh": np.where(np.arange(n) >= 2, np.linspace(0, 33, n), np.nan) if gps else np.nan,
        "is_edge": np.arange(n) < 1, "is_clipped": np.arange(n) == 5,
        "rms": np.linspace(0.1, 1.2, n), "p2p": np.linspace(0.5, 4.0, n), "crest": 2.5,
        "band_1_5": 0.1, "band_5_15": 0.3, "band_15_40": 0.6,
        "score_if": np.linspace(-0.2, 0.1, n),
        "is_anomaly_if": np.arange(n) == 9,
    })
    df["log_rms"] = np.log(df["rms"] + 1e-6)
    df["is_stopped"] = df["has_gps"] & (df["speed_kmh"] < 5) if gps else False
    df["z_speed"] = np.where(df["has_gps"], np.linspace(-1.0, 2.5, n), np.nan) if gps else np.nan
    df["is_anomaly_z"] = False
    if gps:  # しきい値（3）を超えた所を 2 つ（いつもと違う振動の見本）
        df.loc[[7, 9], "z_speed"] = [3.4, 3.1]
        df.loc[[7, 9], "is_anomaly_z"] = True
    return df


def _accel(n_windows: int = 12, fs: float = 40.0) -> pd.DataFrame:
    t = np.arange(int(n_windows * fs)) / fs
    return pd.DataFrame({"t_rel": t, "ax_g": 0.1 * np.sin(2 * np.pi * 8 * t), "ay_g": 1.0 + 0.05 * np.sin(2 * np.pi * 15 * t), "az_g": 0.02 * np.cos(2 * np.pi * 3 * t)})


def build_app_examples() -> dict[str, dict]:
    df = _windows()
    recording = processing.recording_settings(
        {"firmware": "CT125_LOGGER_V3.7", "accel": {"chip": "ADXL345", "bus": "i2c", "odr_hz": 800, "range_g": 16}}, 798.64, 399.32
    )
    summary, payload = export.ride_payload(df, memo="# 例\n家の前で 2 分アイドリングしてから出発", model_version=EXAMPLE_MODEL_VERSION, recording=recording)
    rows = [i for i, flag in enumerate(payload["columns"]["anomaly"]) if flag][:2]
    _, spec, waves = export.extras_payload(df, _accel(), rows)
    nogps_summary, _ = export.ride_payload(_windows(gps=False), model_version=EXAMPLE_MODEL_VERSION)
    rides = export.rides_document([summary, nogps_summary], {"ride_20261108_011304": "2026/11/02の走行", "ride_007": "2026/11/02の走行(1)"})
    rides["generated_at_ms"] = FIXED_GENERATED_AT_MS
    return {"rides.json": rides, "ride.json": payload, "spec.json": spec, "wave.json": waves[0]}


def _pretty(document: dict) -> str:
    """読みやすい JSON（値だけの配列は 1 行にまとめる）。"""
    text = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False)
    return re.sub(r"\[\s+([^\[\]{}]*?)\s+\]", lambda m: "[" + " ".join(m.group(1).split()) + "]", text) + "\n"


SCHEMAS = {"rides.json": "app/rides.schema.json", "ride.json": "app/ride.schema.json", "spec.json": "app/spec.schema.json", "wave.json": "app/wave.schema.json"}


@pytest.mark.parametrize("name", SCHEMAS)
def test_export_matches_app_schema(name):
    validator(SCHEMAS[name]).validate(build_app_examples()[name])


@pytest.mark.parametrize("name", SCHEMAS)
def test_examples_come_from_the_exporter(name):
    built = build_app_examples()[name]
    path = EXAMPLES / name
    if os.environ.get("CT125_WRITE_CONTRACT_EXAMPLES") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_pretty(built).encode("utf-8"))
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(built, allow_nan=False)), (
        f"{path} が書き出しと違います。書き出しを変えたなら CT125_WRITE_CONTRACT_EXAMPLES=1 で作り直してください"
    )


def test_window_columns_match_app_schema():
    columns = load("app/ride.schema.json")["properties"]["columns"]["properties"]
    assert set(export.WINDOW_COLUMNS) | {"t_abs_ms", "cls", "anomaly", "anomaly_score"} == set(columns)
