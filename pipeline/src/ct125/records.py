# -*- coding: utf-8 -*-
"""処理の記録（run.json）・走行の台帳（ledger/rides.json）・モデルの記録（model.json）を作る。

形は contracts/records/ の定義のとおり（tests/test_records.py で確かめる）。ファイルの読み書きはしない。
"""
from __future__ import annotations

import os
import platform
import re
import secrets
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 走行 ID（contracts/common.json の ride_id）。サーバーが付ける ride_<日時> と、上げ直す前の ride_NNN
RIDE_ID_PATTERN = re.compile(r"ride_([0-9]{8}_[0-9]{6}(_[0-9]{1,2})?|[0-9]{3})")
# 処理の ID とモデルの版（contracts/records/）
RUN_ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
MODEL_VERSION_PATTERN = re.compile(r"[0-9]{8}(-[0-9]{6})?")

RUN_SCHEMA = "run/2"  # 2：走行ごとの n_highlights を n_anomalies にした（#71）
LEDGER_SCHEMA = "ledger/1"
MODEL_SCHEMA = "model/1"

JST = timezone(timedelta(hours=9), "JST")  # 走行の名前の日付と、走行 ID の日時（デバイス API が日本時間で付ける）
RIDE_ID_TIME = re.compile(r"ride_([0-9]{8}_[0-9]{6})")
RIDE_NAME = re.compile(r"(?P<base>[0-9]{4}/[0-9]{2}/[0-9]{2}の走行)(?:\((?P<number>[0-9]+)\))?")


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
    import skops
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "scipy": scipy.__version__,
        "scikit-learn": sklearn.__version__,
        "pyarrow": pyarrow.__version__,
        "skops": skops.__version__,
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


def ride_result(ride_id: str, kind: str | None = None, kind_metrics: dict | None = None, n_windows: int | None = None, n_anomalies: int | None = None, error: str | None = None) -> dict:
    return {
        "ride_id": ride_id,
        "status": "failed" if error else "succeeded",
        "kind": kind,
        "kind_metrics": kind_metrics,
        "n_windows": n_windows,
        "n_anomalies": n_anomalies,
        "error": error,
    }


def finish_run(run: dict, finished: datetime, error: str | None = None) -> dict:
    failed = error is not None or any(ride["status"] == "failed" for ride in run["rides"])
    if error is None and failed:
        error = "失敗した走行があります：" + ", ".join(ride["ride_id"] for ride in run["rides"] if ride["status"] == "failed")
    return {**run, "finished_at": iso(finished), "status": "failed" if failed else "succeeded", "error": error}


def public_config(cfg: dict) -> dict:
    """run.json・model.json に残す設定（読み込みの都合で足した内部の値と、PC ごとの値は除く）。"""
    return {key: value for key, value in cfg.items() if not key.startswith("_") and key not in ("local", "aws", "environments")}


# ------------------------------------------------------------------ 走行の台帳
def empty_ledger(now: datetime) -> dict:
    return {"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": {}}


def new_entry(ride_id: str, marker: dict | None) -> dict:
    """台帳の 1 件。marker は raw の upload_complete.json（無ければ None）。"""
    marker = marker or {}
    return {
        "ride_id": ride_id,
        "name": None,  # 台帳に載せるときに name_rides が付ける
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


StartOf = Callable[[str, dict], int | None]  # (走行 ID, 台帳の 1 件) → 走り始めの UNIX ミリ秒（GPS なし・分からなければ None）


def record_run(ledger: dict, run: dict, markers: dict[str, dict | None], publish: bool, now: datetime, start_of: StartOf | None = None) -> dict:
    """処理の結果を台帳に入れた新しい台帳を返す（元は変えない）。

    どの走行にも、この処理の run_id を足す。publish なら、成功した走行の「公開中の結果」をこの処理にし、分類もこの処理のものにする。
    publish でない（ローカルで試した）ときは、分類も公開中の結果も変えない（画面と学習に効かせない）。
    名前の無い走行（新しい走行と、名前を足す前からある走行）には名前を付ける（name_rides）。start_of は名前の日付に使う走り始めの時刻。
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
    return name_rides({"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": dict(sorted(rides.items()))}, start_of)


def point_to_run(ledger: dict, run: dict, now: datetime, start_of: StartOf | None = None) -> dict:
    """run の中で成功した走行の「公開中の結果」を、この run にした新しい台帳。"""
    rides = {ride_id: dict(entry) for ride_id, entry in ledger["rides"].items()}
    for result in run["rides"]:
        entry = rides.get(result["ride_id"])
        if entry is not None and result["status"] == "succeeded":
            entry["published_run"] = run["run_id"]
            entry["kind"] = result["kind"]
            entry["kind_metrics"] = result["kind_metrics"]
    return name_rides({"schema": LEDGER_SCHEMA, "updated_at": iso(now), "rides": rides}, start_of)


def needs_names(ledger: dict) -> bool:
    return any(not entry.get("name") for entry in ledger["rides"].values())


def name_rides(ledger: dict, start_of: StartOf | None = None) -> dict:
    """名前の無い走行に名前を付けた台帳（元は変えない。付いている名前は変えない）。

    名前は「YYYY/MM/DDの走行」。同じ日の 2 本目は「(1)」、3 本目は「(2)」を後ろに付ける。
    日付は走り始めた日（start_of が返す GPS の時刻、日本時間）。GPS なしは届いた日（走行 ID の日時、無ければ受け取った日時）。
    同じ日の番号は、その日に付いている名前の続きから、走り始めた順（分からなければ届いた順）に付ける。
    後から前の時刻の走行が届いても、付いている名前は付け直さない（同じ走行の名前が変わらないように）。
    """
    unnamed = [ride_id for ride_id, entry in ledger["rides"].items() if not entry.get("name")]
    if not unnamed:
        return ledger
    rides = {ride_id: dict(entry) for ride_id, entry in ledger["rides"].items()}
    last_number: dict[str, int] = {}  # 名前の日付の部分 → 付いている番号の一番大きいもの（番号なしは 0）
    for entry in rides.values():
        match = RIDE_NAME.fullmatch(entry.get("name") or "")
        if match:
            last_number[match["base"]] = max(last_number.get(match["base"], -1), int(match["number"] or 0))

    def moment(ride_id: str) -> datetime | None:
        start_ms = start_of(ride_id, rides[ride_id]) if start_of else None
        if start_ms is not None:
            return datetime.fromtimestamp(start_ms / 1000, JST)
        return arrived_at(ride_id, rides[ride_id])

    moments = {ride_id: moment(ride_id) for ride_id in unnamed}
    for ride_id in sorted(unnamed, key=lambda r: (moments[r] is None, moments[r].timestamp() if moments[r] else 0.0, r)):
        when = moments[ride_id]
        if when is None:  # 日時が何も分からない走行（古い ride_NNN で、受け取った日時も無い）は走行 ID のまま
            rides[ride_id]["name"] = ride_id
            continue
        base = f"{when:%Y/%m/%d}の走行"
        number = last_number.get(base, -1) + 1
        last_number[base] = number
        rides[ride_id]["name"] = base if number == 0 else f"{base}({number})"
    rides = {ride_id: _with_name_first(entry) for ride_id, entry in rides.items()}
    return {**ledger, "rides": rides}


def arrived_at(ride_id: str, entry: dict) -> datetime | None:
    """届いた日時（日本時間）。走行 ID の日時（デバイス API が受け取ったときに付ける）、無ければ受け取った日時。"""
    match = RIDE_ID_TIME.match(ride_id)
    if match:
        return datetime.strptime(match[1], "%Y%m%d_%H%M%S").replace(tzinfo=JST)
    received = _iso_or_none(entry.get("received_at"))
    return datetime.fromisoformat(received.replace("Z", "+00:00")).astimezone(JST) if received else None


def _with_name_first(entry: dict) -> dict:
    """ride_id の次に name を置く（台帳を読みやすくするため。中身は変えない）。"""
    return {"ride_id": entry["ride_id"], "name": entry["name"], **entry}


def _iso_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return iso(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


# ------------------------------------------------------------------ モデルの記録
def model_record(version: str, created: datetime, where: str, commit: str | None, run_id: str, cfg: dict, train: list[dict], excluded: list[dict], summary: dict, forest: dict) -> dict:
    """model.json の中身。forest は Isolation Forest の特徴量・分位点の割合・しきい値・学習した窓の数（model.fit_models の返り値）。"""
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
        "forest": forest,
    }


KIND_NAMES = {"desk": "机上", "idle": "停車", "ride": "実走", "ride_nogps": "実走（GPS なし）"}
REASON_NAMES = {"desk": "机上の試験", "ride_nogps": "GPS が足りない", "deleted": "画面で消した", "failed": "処理に失敗した", "unclassified": "分類できなかった"}


def _forest_lines(forest: dict | None) -> list[str]:
    if not forest:
        return []
    return [f"- Isolation Forest：特徴量 {', '.join(forest['features'])}。GPS のある窓 {forest['n_train']} で学習。しきい値 {forest['threshold']:.4f}（学習の窓の score_if の {forest['quantile']} 分位点）"]


def model_notes(record: dict) -> str:
    """notes.md の下書き（要約を自動で書く。気づいたことは人が足す）。"""
    s = record["summary"]
    lines = [
        f"# モデル {record['version']}",
        "",
        f"- 作った日時：{record['created_at']}（{'Lambda' if record['where'] == 'lambda' else 'ローカル'}、コミット {record['commit'] or '不明'}、処理 {record['run_id']}）",
        f"- 学習に使った窓：{record['train']['n_windows']}（先頭・末尾 {record['config'].get('edge_sec', '?')} 秒と振り切れの窓を除く）",
        f"- 速度補正ベースライン：ビン {s['baseline_bins']}、学習した窓 {s['baseline_n_train']}（GPS のある窓）",
        f"- 学習した窓のうち z_speed の候補 {s['n_anomaly_z']}、Isolation Forest の外れ {s['n_anomaly_if']}、速度を足した Isolation Forest の判定 {s.get('n_anomaly_sif', '?')}",
        *_forest_lines(record.get("forest")),
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
