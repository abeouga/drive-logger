# -*- coding: utf-8 -*-
"""テスト用の小さな SD の記録（contracts/sd/ の形）を作る。

kind：desk（振動なし）・idle（その場でアイドリング）・ride（東へ 36 km/h で走る）・ride_nogps（走るが GPS が取れない）
"""
from __future__ import annotations

import json

import numpy as np

AMPLITUDE_G = {"desk": 0.01, "idle": 0.13, "ride": 0.5, "ride_nogps": 0.5}
START_LAT, START_LON = 35.0, 135.0
METERS_PER_DEG_LON = 111320 * np.cos(np.deg2rad(START_LAT))


def session_files(kind: str, seconds: int = 150, fs: float = 100.0, seed: int = 0, memo: str | None = None) -> dict[str, bytes]:
    rng = np.random.default_rng(seed)
    n = int(seconds * fs)
    t0_us = 1_000_000
    t_us = t0_us + (np.arange(n) * 1e6 / fs).astype(np.int64)
    amp = AMPLITUDE_G[kind]
    ax, ay, az = rng.normal(0, amp, n), 1.0 + rng.normal(0, amp, n), rng.normal(0, amp, n)
    accel = "n,t_us,ax_g,ay_g,az_g\n" + "".join(f"{i},{t},{x:.4f},{y:.4f},{z:.4f}\n" for i, (t, x, y, z) in enumerate(zip(t_us, ax, ay, az)))

    rows = ["t_rx_us,utc,date,status,fix,sats,hdop,lat,lon,speed_kmh,course_deg"]
    for i in range(seconds):
        t_rx = t0_us + i * 1_000_000 + 500
        hh, mm, ss = 5, (i // 60) % 60, i % 60
        utc = f"{hh:02d}{mm:02d}{ss:02d}.000"
        if kind == "ride_nogps":
            rows.append(f"{t_rx},{utc},021126,V,0,0,99.9,,,,")
            continue
        moving = kind == "ride"
        lon = START_LON + (i * 10.0 / METERS_PER_DEG_LON if moving else 0.0)
        speed = 36.0 if moving else 0.5
        rows.append(f"{t_rx},{utc},021126,A,1,8,1.0,{START_LAT:.6f},{lon:.6f},{speed:.2f},90.0")
    gps = "\n".join(rows) + "\n"

    meta = {
        "spec": "データ仕様.md v2", "firmware": "CT125_LOGGER_V3.2", "build": "Nov  9 2026 01:00:00",
        "clock": "t_us = ESP32 esp_timer（起動からのマイクロ秒）",
        "accel": {"chip": "ADXL345", "odr_hz": fs, "range_g": 16, "lsb_g": 0.0039, "unit": "g", "axes": "センサー基板の軸のまま"},
        "gps": {"chip": "ATGM336H", "baud": 9600, "t_rx_us": "RMC文の先頭を受け取った時刻", "pps_pin": -1},
        "mounting": "未記入（取り付けたら notes.md に書く）", "flush_ms": 1000,
    }
    files = {
        "accel.csv": accel.encode("utf-8"),
        "gps.csv": gps.encode("utf-8"),
        "events.csv": f"t_us,type,detail\n{t0_us},boot,CT125_LOGGER_V3.2\n".encode("utf-8"),
        "meta.json": json.dumps(meta, ensure_ascii=False).encode("utf-8"),
    }
    if memo:
        files["notes.md"] = memo.encode("utf-8")
    return files


def marker(ride_id: str, files: dict[str, bytes], device_id: str = "d01", local_session: str = "ride_013") -> bytes:
    """デバイス API が置く完了の印（contracts/upload/upload_complete.schema.json）。"""
    return json.dumps({
        "ride_id": ride_id, "files": sorted(files), "uploaded_at": "2026-11-09T01:00:00+00:00",
        "source": "device", "device_id": device_id, "local_session": local_session,
    }).encode("utf-8")


def put_ride(store, prefix: str, ride_id: str, kind: str, seed: int = 0, with_marker: bool = True, **kwargs) -> None:
    files = session_files(kind, seed=seed, **kwargs)
    for name, data in files.items():
        store.put(f"{prefix}{ride_id}/{name}", data, "application/octet-stream")
    if with_marker:
        store.put(f"{prefix}{ride_id}/upload_complete.json", marker(ride_id, files), "application/json")
