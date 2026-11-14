# -*- coding: utf-8 -*-
"""異常スコア（docs/analysis_policy.md 4.）。

- 速度補正ベースライン：速度を一定幅（既定 5 km/h）でビン分けし、各ビンで log_rms の中央値と MAD を求める。
  z_speed = (log_rms − 中央値) / (1.4826 × MAD)。大きいほど「その速度としては振動が大きい」。
- Isolation Forest：振動の特徴量に速度を足して学習する（#81）。速度が分からない窓（GPS なし）は学習に使わず、スコアも付けない。
  score_if は decision_function の符号反転（大きいほど異常）。しきい値は、学習に使った窓の score_if の分位点
  （config の model.anomaly_quantile）で、学習のときに求めて model.json の forest に保存する。
  速度を足す前に作った版（model.json に forest が無い）は、振動の特徴量だけで読む（LEGACY_FOREST_INFO）。
- 画面に出す判定（judge_anomalies）の方法は、config の model.anomaly_method で選ぶ（speed_baseline か speed_iforest）。
- 保存は skops（pickle と違い、読み込んでもファイルの中のコードが動かない。#23）。読むときは信頼する型を決め打ちで渡し、
  それ以外の型が入っていれば止める。

学習データは健康な車両の走行のみ。故障データは含まれていないので、ここで出すのは
「速度で補正した正常時のベースラインからの逸脱」であり、故障の予測ではない。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import skops.io as sio
from sklearn.ensemble import IsolationForest

MAD_SCALE = 1.4826
DEFAULT_Z_THRESHOLD = 3.0  # config の model.z_threshold が無いとき
DEFAULT_ANOMALY_QUANTILE = 0.999  # config の model.anomaly_quantile が無いとき
VIBRATION_FEATURES = ["log_rms", "p2p", "std", "crest", "jerk_rms", "band_1_5", "band_5_15", "band_15_40"]
IF_FEATURES = [*VIBRATION_FEATURES, "speed_kmh"]
# 速度を足す前（#81 より前）に作った版。振動の特徴量だけで学習していて、しきい値を持たない（speed_iforest には使えない）
LEGACY_FOREST_INFO = {"features": VIBRATION_FEATURES, "quantile": None, "threshold": None, "n_train": None}


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
    """score_if（大きいほど異常）と is_anomaly_if（モデルの contamination に基づく外れ）。欠損のある窓（速度の無い窓も）は NaN。"""
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


def forest_threshold(scores: np.ndarray, quantile: float) -> float:
    """学習に使った窓の score_if の分位点（quantile=0.999 なら、学習の窓の上位 0.1% がこれを超える）。"""
    if not 0 < quantile < 1:
        raise ValueError(f"model.anomaly_quantile は 0 より大きく 1 より小さい値にしてください：{quantile}")
    s = np.asarray(scores, dtype=float)
    s = s[np.isfinite(s)]
    if len(s) == 0:
        raise ValueError("しきい値を求めるスコアがありません")
    return float(np.quantile(s, quantile))


def fit_models(all_windows: pd.DataFrame, mcfg: dict) -> tuple[dict, IsolationForest, dict]:
    """学習：全走行の windows から、速度補正ベースラインと、速度を足した Isolation Forest を作る。

    どちらも速度の分かる窓（has_gps）だけで学習する。3 つめの返り値（forest_info）は、Isolation Forest の
    特徴量・分位点の割合・しきい値・学習した窓の数。model.json の forest に入れ、点数付けのときに読む。
    """
    train = all_windows[training_mask(all_windows)]
    located = train[train["has_gps"].fillna(False).astype(bool)]
    baseline = fit_speed_baseline(located, mcfg.get("speed_bin_kmh", 5.0), mcfg.get("baseline_min_count", 10))
    forest = fit_isolation_forest(located, mcfg.get("contamination", 0.03), mcfg.get("n_estimators", 300), mcfg.get("random_state", 0), IF_FEATURES)
    scores = apply_isolation_forest(located, forest, IF_FEATURES)["score_if"].to_numpy(float)
    quantile = float(mcfg.get("anomaly_quantile", DEFAULT_ANOMALY_QUANTILE))
    info = {"features": list(IF_FEATURES), "quantile": quantile, "threshold": forest_threshold(scores, quantile), "n_train": int(np.isfinite(scores).sum())}
    return baseline, forest, info


def apply_models(windows: pd.DataFrame, baseline: dict, forest: IsolationForest, mcfg: dict, stop_speed_kmh: float = 5.0, forest_info: dict | None = None) -> pd.DataFrame:
    """推論：学習済みのモデルで、windows（1 走行でも全走行でもよい）にスコア列を付けて返す。

    z_speed は速度のある全窓に付けるが、is_anomaly_z は走行中（speed ≥ stop_speed_kmh）の窓だけに立てる。
    停止ビン（0〜5 km/h）はアイドリングの窓が大半で MAD がとても小さく、発進・取り回しの窓が z>3 になってしまうため。

    is_anomaly_sif（速度を足した Isolation Forest の判定）は、次の全部に当てはまる窓だけに立てる。
    - score_if が forest_info のしきい値を超える
    - その速度でのふだんより振動が大きい（z_speed > 0。log_rms が、その速度のビンの中央値より大きい）。
      Isolation Forest は「まれな組み合わせ」を拾うので、静かすぎる窓もスコアが高くなる。それは判定に入れない
    - 走行中（is_anomaly_z と同じ理由で、停止中の窓は入れない）
    forest_info を省くと、速度を足す前の版（LEGACY_FOREST_INFO）として読み、is_anomaly_sif はすべて False。
    """
    info = forest_info or LEGACY_FOREST_INFO
    out = windows.copy()
    out["is_stopped"] = out["has_gps"] & (out["speed_kmh"] < stop_speed_kmh)
    out["z_speed"] = apply_speed_baseline(out, baseline)
    out["is_anomaly_z"] = (out["z_speed"] > mcfg.get("z_threshold", DEFAULT_Z_THRESHOLD)) & ~out["is_stopped"]
    out = pd.concat([out, apply_isolation_forest(out, forest, info["features"])], axis=1)
    if info.get("threshold") is None:
        out["is_anomaly_sif"] = False
    else:
        louder = out["z_speed"].fillna(-np.inf) > 0
        moving = ~out["is_stopped"].fillna(False).astype(bool)
        out["is_anomaly_sif"] = (out["score_if"].fillna(-np.inf) > info["threshold"]) & louder & moving
    return out


ANOMALY_SPEED_BASELINE = "speed_baseline"
ANOMALY_SPEED_IFOREST = "speed_iforest"
ANOMALY_NONE = "none"
ANOMALY_METHODS = (ANOMALY_SPEED_BASELINE, ANOMALY_SPEED_IFOREST)


@dataclass(frozen=True)
class AnomalyRule:
    """画面に出す判定の決め方：方法（config の model.anomaly_method）と、そのしきい値。"""

    method: str
    threshold: float


DEFAULT_RULE = AnomalyRule(ANOMALY_SPEED_BASELINE, DEFAULT_Z_THRESHOLD)


def anomaly_rule(mcfg: dict, forest_info: dict | None = None) -> AnomalyRule:
    """config と、今使うモデルの forest_info から、判定の決め方を作る。

    speed_iforest を選んだのに、モデルがしきい値を持たない（速度を足す前の版）ときは止める。学習し直してから切り替える。
    """
    method = mcfg.get("anomaly_method", ANOMALY_SPEED_BASELINE)
    if method == ANOMALY_SPEED_BASELINE:
        return AnomalyRule(method, float(mcfg.get("z_threshold", DEFAULT_Z_THRESHOLD)))
    if method == ANOMALY_SPEED_IFOREST:
        threshold = (forest_info or LEGACY_FOREST_INFO).get("threshold")
        if threshold is None:
            raise ValueError("このモデルの版は、速度を足した Isolation Forest のしきい値を持っていません（#81 より前の版）。学習し直してから speed_iforest を使ってください")
        return AnomalyRule(method, float(threshold))
    raise ValueError(f"model.anomaly_method は {' か '.join(ANOMALY_METHODS)} にしてください：{method}")


def judge_anomalies(scored: pd.DataFrame, rule: AnomalyRule = DEFAULT_RULE) -> tuple[str, np.ndarray, np.ndarray, float | None]:
    """画面に出す「いつもと違う振動」の判定：(方法, 判定, 判定に使ったスコア, しきい値)。scored は apply_models の結果。

    - 速度のある窓がある走行：rule の方法で判定する
      - speed_baseline：is_anomaly_z（走行中かつ z_speed > z_threshold）。スコアは z_speed
      - speed_iforest：is_anomaly_sif（走行中・振動が大きい側・score_if > しきい値）。スコアは score_if
    - 速度のある窓が無い走行（GPS なし）：判定しない。判定はすべて False、スコアは NaN、しきい値は None

    上位 N 件で埋めることはしない。しきい値を超えた窓が無ければ 0 件のまま。
    モデルを差し替えるときは、ここに新しい方法を足す（画面は方法の名前・しきい値・判定だけを読む）。
    """
    n = len(scored)
    z = scored["z_speed"].to_numpy(float)
    if not np.isfinite(z).any():
        return ANOMALY_NONE, np.zeros(n, dtype=bool), np.full(n, np.nan), None
    if rule.method == ANOMALY_SPEED_IFOREST:
        return rule.method, scored["is_anomaly_sif"].fillna(False).to_numpy(bool), scored["score_if"].to_numpy(float), rule.threshold
    return ANOMALY_SPEED_BASELINE, scored["is_anomaly_z"].fillna(False).to_numpy(bool), z, rule.threshold


def score_windows(all_windows: pd.DataFrame, mcfg: dict, stop_speed_kmh: float = 5.0) -> tuple[pd.DataFrame, dict, IsolationForest, dict]:
    """学習してから、同じ windows にスコア列を付けて返す（fit_models → apply_models）。"""
    baseline, forest, info = fit_models(all_windows, mcfg)
    scored = apply_models(all_windows, baseline, forest, mcfg, stop_speed_kmh, info)
    return scored, baseline, forest, info
