# -*- coding: utf-8 -*-
"""処理の記録（run.json）・走行の台帳（ledger/rides.json）・モデルの記録（model.json）を作る。

形は contracts/records/ の定義のとおり（tests/test_records.py で確かめる）。ファイルの読み書きはしない。
"""
from __future__ import annotations

import os
import platform
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RUN_SCHEMA = "run/1"
LEDGER_SCHEMA = "ledger/1"
MODEL_SCHEMA = "model/1"


# ------------------------------------------------------------------ 名前と時刻
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(moment: datetime) -> str:
    """<UTC の日時>-<6 桁の 16 進>（例 20261109T031500Z-3f9a1c）。並べると時刻の順になる。"""
    return f"{moment.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def new_model_version(moment: datetime) -> str:
    """モデルの版：<UTC の日時>（例 20261109-031500）。ローカルと Lambda でそろえる。"""
    return f"{moment.astimezone(timezone.utc):%Y%m%d-%H%M%S}"


def code_commit() -> str | None:
    """コードのコミット。Lambda ではコンテナを作るときに入れた CT125_COMMIT、手元では git から。分からなければ None。"""
    if os.environ.get("CT125_COMMIT"):
        return os.environ["CT125_COMMIT"]
    repo = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--", "pipeline/src", "pipeline/config"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return f"{commit}-dirty" if dirty else commit or None


def library_versions() -> dict[str, str]:
    """学習・推論に効くライブラリの版（model.json に残し、読むときに突き合わせる）。"""
    import numpy
    import pandas
    import pyarrow
    import scipy
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "scikit-learn": sklearn.__version__,
        "pyarrow": pyarrow.__version__,
    }


def library_mismatches(recorded: dict[str, str], current: dict[str, str]) -> list[str]:
    """学習したときと今で違うライブラリ（python は 3.12 のような版の上 2 つだけを比べる）。"""
    out = []
    for name, version in recorded.items():
        now = current.get(name)
        if name == "python":
            same = now is not None and now.split(".")[:2] == version.split(".")[:2]
        else:
            same = now == version
        if not same:
            out.append(f"{name}（学習 {version}、今 {now}）")
    return out


# ------------------------------------------------------------------ 処理の記録（run.json）
def start_run(run_id: str, action: str, where: str, commit: str | None, cfg: dict, started: datetime) -> dict:
    return {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "action": action,
        "where": where,
        "commit": commit,
        "started_at": iso(started),
        "finished_at": None,
        "status": "running",
        "error": None,
        "config": public_config(cfg),
        "model_version": None,
        "rides": [],
    }


def ride_result(ride_id: str, kind: str | None = None, kind_metrics: dict | None = None, n_windows: int | None = None, n_highlights: int | None = None, error: str | None = None) -> dict:
    return {
        "ride_id": ride_id,
        "status": "failed" if error else "succeeded",
        "kind": kind,
        "kind_metrics": kind_metrics,
        "n_windows": n_windows,
        "n_highlights": n_highlights,
        "error": error,
    }


def finish_run(run: dict, finished: datetime, error: str | None = None) -> dict:
    failed = error is not None or any(ride["status"] == "failed" for ride in run["rides"])
    if error is None and failed:
        error = "失敗した走行があります：" + ", ".join(ride["ride_id"] for ride in run["rides"] if ride["status"] == "failed")
    return {**run, "finished_at": iso(finished), "status": "failed" if failed else "succeeded", "error": error}


def public_config(cfg: dict) -> dict:
    """run.json・model.json に残す設定（読み込みの都合で足した内部の値と、PC ごとの値は除く）。"""
    return {key: value for key, value in cfg.items() if not key.startswith("_") and key not in ("local", "aws")}


# ------------------------------------------------------------------ 走行の台帳
def empty_ledger(now: datetime) -> dict:
    return {"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": {}}


def new_entry(ride_id: str, marker: dict | None) -> dict:
    """台帳の 1 件。marker は raw の upload_complete.json（無ければ None）。"""
    marker = marker or {}
    return {
        "ride_id": ride_id,
        "original_name": None,
        "device_id": marker.get("device_id"),
        "local_session": marker.get("local_session"),
        "source": marker.get("source") or "legacy",
        "received_at": _iso_or_none(marker.get("uploaded_at")),
        "kind": None,
        "kind_metrics": None,
        "deleted": False,
        "deleted_at": None,
        "deleted_by": None,
        "published_run": None,
        "runs": [],
    }


def record_run(ledger: dict, run: dict, markers: dict[str, dict | None], publish: bool, now: datetime) -> dict:
    """処理の結果を台帳に入れた新しい台帳を返す（元は変えない）。

    どの走行にも、この処理の run_id を足す。publish なら、成功した走行の「公開中の結果」をこの処理にし、分類もこの処理のものにする。
    publish でない（ローカルで試した）ときは、分類も公開中の結果も変えない（画面と学習に効かせない）。
    """
    rides = {ride_id: dict(entry) for ride_id, entry in ledger["rides"].items()}
    for result in run["rides"]:
        ride_id = result["ride_id"]
        entry = rides.get(ride_id) or new_entry(ride_id, markers.get(ride_id))
        entry["runs"] = [run["run_id"]] + [r for r in entry["runs"] if r != run["run_id"]]
        if publish and result["status"] == "succeeded":
            entry["kind"] = result["kind"]
            entry["kind_metrics"] = result["kind_metrics"]
            entry["published_run"] = run["run_id"]
        rides[ride_id] = entry
    return {"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": dict(sorted(rides.items()))}


def point_to_run(ledger: dict, run: dict, now: datetime) -> dict:
    """run の中で成功した走行の「公開中の結果」を、この run にした新しい台帳。"""
    rides = {ride_id: dict(entry) for ride_id, entry in ledger["rides"].items()}
    for result in run["rides"]:
        entry = rides.get(result["ride_id"])
        if entry is not None and result["status"] == "succeeded":
            entry["published_run"] = run["run_id"]
            entry["kind"] = result["kind"]
            entry["kind_metrics"] = result["kind_metrics"]
    return {"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": rides}


def _iso_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return iso(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


# ------------------------------------------------------------------ モデルの記録
def model_record(version: str, created: datetime, where: str, commit: str | None, run_id: str, cfg: dict, train: list[dict], excluded: list[dict], summary: dict) -> dict:
    return {
        "schema": MODEL_SCHEMA,
        "version": version,
        "created_at": iso(created),
        "where": where,
        "commit": commit,
        "run_id": run_id,
        "libraries": library_versions(),
        "config": {key: cfg[key] for key in ("model", "stop_speed_kmh", "classify", "window_sec", "edge_sec", "clip_g") if key in cfg},
        "train": {"rides": train, "n_windows": int(sum(item["n_windows"] for item in train))},
        "excluded": excluded,
        "summary": summary,
    }


KIND_NAMES = {"desk": "机上", "idle": "停車", "ride": "実走", "ride_nogps": "実走（GPS なし）"}
REASON_NAMES = {"desk": "机上の試験", "ride_nogps": "GPS が足りない", "deleted": "画面で消した", "failed": "処理に失敗した", "unclassified": "分類できなかった"}


def model_notes(record: dict) -> str:
    """notes.md の下書き（要約を自動で書く。気づいたことは人が足す）。"""
    s = record["summary"]
    lines = [
        f"# モデル {record['version']}",
        "",
        f"- 作った日時：{record['created_at']}（{'Lambda' if record['where'] == 'lambda' else 'ローカル'}、コミット {record['commit'] or '不明'}、処理 {record['run_id']}）",
        f"- 学習に使った窓：{record['train']['n_windows']}（先頭・末尾 {record['config'].get('edge_sec', '?')} 秒と振り切れの窓を除く）",
        f"- 速度補正ベースライン：ビン {s['baseline_bins']}、学習した窓 {s['baseline_n_train']}（GPS のある窓）",
        f"- 学習した窓のうち z_speed の候補 {s['n_anomaly_z']}、Isolation Forest の外れ {s['n_anomaly_if']}",
        "",
        "## 学習に使った走行",
        "",
        "| 走行 | 分類 | 窓 |",
        "|---|---|---|",
        *[f"| {item['ride_id']} | {KIND_NAMES.get(item['kind'], item['kind'])} | {item['n_windows']} |" for item in record["train"]["rides"]],
        "",
        "## 使わなかった走行",
        "",
        "| 走行 | 理由 |",
        "|---|---|",
        *[f"| {item['ride_id']} | {REASON_NAMES.get(item['reason'], item['reason'])} |" for item in record["excluded"]],
        "",
        "## ライブラリ",
        "",
        ", ".join(f"{name} {version}" for name, version in record["libraries"].items()),
        "",
        "## 気づいたこと（人が書く）",
        "",
        "- ",
        "",
    ]
    return "\n".join(lines)
