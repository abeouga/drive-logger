# -*- coding: utf-8 -*-
"""異常スコア（計画書フェーズ 2）。

- 速度補正ベースライン：速度を一定幅（既定 5 km/h）でビン分けし、各ビンで log_rms の中央値と MAD を求める。
  z_speed = (log_rms − 中央値) / (1.4826 × MAD)。大きいほど「その速度としては振動が大きい」。
- Isolation Forest：振動特徴量だけで学習する（速度は使わない）。GPS なし走行にもスコアを付けるため。
  score_if は decision_function の符号反転（大きいほど異常）。
- 保存は skops（pickle と違い、読み込んでもファイルの中のコードが動かない。#23）。読むときは信頼する型を決め打ちで渡し、
  それ以外の型が入っていれば止める。

学習データは健康な車両の走行のみ。故障データは含まれていないので、ここで出すのは
「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import skops.io as sio
from sklearn.ensemble import IsolationForest

MAD_SCALE = 1.4826
DEFAULT_Z_THRESHOLD = 3.0  # config の model.z_threshold が無いとき
IF_FEATURES = ["log_rms", "p2p", "std", "crest", "jerk_rms", "band_1_5", "band_5_15", "band_15_40"]


# ------------------------------------------------------------------ 速度補正ベースライン
def fit_speed_baseline(df: pd.DataFrame, bin_kmh: float = 5.0, min_count: int = 10, target: str = "log_rms") -> dict:
    """速度ビンごとの中央値と MAD。ビンの窓数が min_count 未満なら、十分な窓がある最寄りのビンの値を借りる。

    df は has_gps=True かつ speed_kmh が有限の学習窓。返り値は JSON にできる dict。
    """
    d = df[np.isfinite(df["speed_kmh"]) & np.isfinite(df[target])]
    if len(d) == 0:
        raise ValueError("ベースラインの学習に使える窓がありません")
    vmax = float(d["speed_kmh"].max())
    n_bins = int(np.floor(vmax / bin_kmh)) + 1
    edges = np.arange(n_bins + 1) * bin_kmh
    idx = np.clip(np.floor(d["speed_kmh"].to_numpy() / bin_kmh).astype(int), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        v = d[target].to_numpy()[idx == b]
        if len(v):
            med = float(np.median(v))
            mad = float(np.median(np.abs(v - med)))
        else:
            med, mad = np.nan, np.nan
        rows.append(dict(bin=b, lo=float(edges[b]), hi=float(edges[b + 1]), n=int(len(v)), median=med, mad=mad, source_bin=b))
    good = [r for r in rows if r["n"] >= min_count and r["mad"] > 0]
    if not good:
        raise ValueError(f"窓数 {min_count} 以上のビンがありません")
    for r in rows:
        if r["n"] < min_count or not (r["mad"] > 0):
            src = min(good, key=lambda g: abs(g["bin"] - r["bin"]))
            r.update(median=src["median"], mad=src["mad"], source_bin=src["bin"])
    return {"target": target, "bin_kmh": float(bin_kmh), "min_count": int(min_count), "mad_scale": MAD_SCALE, "n_train": int(len(d)), "bins": rows}


def apply_speed_baseline(df: pd.DataFrame, baseline: dict) -> pd.Series:
    """各窓の z_speed。速度がない窓（has_gps=False）は NaN。学習時の最大速度を超える窓は最後のビンを使う。"""
    bins = baseline["bins"]
    bw = baseline["bin_kmh"]
    med = np.array([b["median"] for b in bins])
    mad = np.array([b["mad"] for b in bins])
    spd = df["speed_kmh"].to_numpy(float)
    x = df[baseline["target"]].to_numpy(float)
    ok = np.isfinite(spd) & np.isfinite(x)
    z = np.full(len(df), np.nan)
    i = np.clip(np.floor(np.nan_to_num(spd, nan=0.0) / bw).astype(int), 0, len(bins) - 1)
    z[ok] = (x[ok] - med[i[ok]]) / (baseline["mad_scale"] * mad[i[ok]])
    return pd.Series(z, index=df.index, name="z_speed")


def save_baseline(baseline: dict, path: Path | str) -> None:
    Path(path).write_text(json.dumps(baseline, ensure_ascii=False, indent=1), encoding="utf-8")


def load_baseline(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Isolation Forest
def fit_isolation_forest(df: pd.DataFrame, contamination: float = 0.03, n_estimators: int = 300, random_state: int = 0, features: list[str] = IF_FEATURES) -> IsolationForest:
    X = df[features].to_numpy(float)
    X = X[np.isfinite(X).all(axis=1)]
    model = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=random_state)
    model.fit(X)
    return model


def apply_isolation_forest(df: pd.DataFrame, model: IsolationForest, features: list[str] = IF_FEATURES) -> pd.DataFrame:
    """score_if（大きいほど異常）と is_anomaly_if（モデルの contamination に基づく判定）。欠損のある窓は NaN。"""
    X = df[features].to_numpy(float)
    ok = np.isfinite(X).all(axis=1)
    score = np.full(len(df), np.nan)
    flag = np.zeros(len(df), dtype=bool)
    if ok.any():
        score[ok] = -model.decision_function(X[ok])
        flag[ok] = model.predict(X[ok]) == -1
    return pd.DataFrame({"score_if": score, "is_anomaly_if": flag}, index=df.index)


# skops が既定で信頼しない型のうち、Isolation Forest に入っているもの（skops.io.get_untrusted_types で確かめた）。
# ライブラリの版を上げて型が増えたら、読み込みが UntrustedTypesFoundException で止まるので、確かめてから足す
FOREST_TRUSTED_TYPES = ["sklearn.tree._tree.Tree"]


def dump_forest(model: IsolationForest) -> bytes:
    return sio.dumps(model)


def load_forest(data: bytes) -> IsolationForest:
    """skops で読む。信頼する型（FOREST_TRUSTED_TYPES）以外が入っていれば UntrustedTypesFoundException で止まる。"""
    model = sio.loads(data, trusted=FOREST_TRUSTED_TYPES)
    if not isinstance(model, IsolationForest):
        raise TypeError(f"Isolation Forest ではありません：{type(model).__name__}")
    return model


def save_model(model: IsolationForest, path: Path | str) -> None:
    Path(path).write_bytes(dump_forest(model))


def load_model(path: Path | str) -> IsolationForest:
    return load_forest(Path(path).read_bytes())


# ------------------------------------------------------------------ まとめて
def training_mask(df: pd.DataFrame) -> pd.Series:
    """学習に使う窓：先頭・末尾でなく、振り切れていない窓。"""
    return (~df["is_edge"]) & (~df["is_clipped"])


def fit_models(all_windows: pd.DataFrame, mcfg: dict) -> tuple[dict, IsolationForest]:
    """学習：全走行の windows から、速度補正ベースラインと Isolation Forest を作る。"""
    train = all_windows[training_mask(all_windows)]
    baseline = fit_speed_baseline(train[train["has_gps"]], mcfg.get("speed_bin_kmh", 5.0), mcfg.get("baseline_min_count", 10))
    forest = fit_isolation_forest(train, mcfg.get("contamination", 0.03), mcfg.get("n_estimators", 300), mcfg.get("random_state", 0))
    return baseline, forest


def apply_models(windows: pd.DataFrame, baseline: dict, forest: IsolationForest, mcfg: dict, stop_speed_kmh: float = 5.0) -> pd.DataFrame:
    """推論：学習済みのモデルで、windows（1 走行でも全走行でもよい）にスコア列を付けて返す。

    z_speed は速度のある全窓に付けるが、is_anomaly_z は走行中（speed ≥ stop_speed_kmh）の窓だけに立てる。
    停止ビン（0〜5 km/h）はアイドリングの窓が大半で MAD がとても小さく、発進・取り回しの窓が z>3 になってしまうため。
    """
    out = windows.copy()
    out["is_stopped"] = out["has_gps"] & (out["speed_kmh"] < stop_speed_kmh)
    out["z_speed"] = apply_speed_baseline(out, baseline)
    out["is_anomaly_z"] = (out["z_speed"] > mcfg.get("z_threshold", DEFAULT_Z_THRESHOLD)) & ~out["is_stopped"]
    return pd.concat([out, apply_isolation_forest(out, forest)], axis=1)


ANOMALY_SPEED_BASELINE = "speed_baseline"
ANOMALY_NONE = "none"


def judge_anomalies(scored: pd.DataFrame) -> tuple[str, np.ndarray, np.ndarray]:
    """画面に出す「いつもと違う振動」の判定：(方法, 判定, 判定に使ったスコア)。scored は apply_models の結果。

    - 速度のある窓がある走行：速度補正ベースライン（is_anomaly_z。走行中かつ z_speed > z_threshold）。スコアは z_speed
    - 速度のある窓が無い走行（GPS なし）：判定しない。Isolation Forest は速度を使わず、速く走った所や
      静かすぎる所を拾うため、そのまま「いつもと違う振動」としては出さない（#71）。判定はすべて False、スコアは NaN

    上位 N 件で埋めることはしない。しきい値を超えた窓が無ければ 0 件のまま。
    モデルを差し替えるときは、ここに新しい方法を足す（画面は方法の名前と判定だけを読む）。
    """
    n = len(scored)
    z = scored["z_speed"].to_numpy(float)
    if np.isfinite(z).any():
        return ANOMALY_SPEED_BASELINE, scored["is_anomaly_z"].fillna(False).to_numpy(bool), z
    return ANOMALY_NONE, np.zeros(n, dtype=bool), np.full(n, np.nan)


def score_windows(all_windows: pd.DataFrame, mcfg: dict, stop_speed_kmh: float = 5.0) -> tuple[pd.DataFrame, dict, IsolationForest]:
    """学習してから、同じ windows にスコア列を付けて返す（fit_models → apply_models）。"""
    baseline, forest = fit_models(all_windows, mcfg)
    scored = apply_models(all_windows, baseline, forest, mcfg, stop_speed_kmh)
    return scored, baseline, forest
