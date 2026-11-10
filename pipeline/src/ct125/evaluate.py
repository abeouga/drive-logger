# -*- coding: utf-8 -*-
"""判定の確かめ：1 走行ずつ抜いて学習し、抜いた走行に点数を付ける（#76・#81）。

正解のラベルが無いので、精度は出さない（DEV_PLAN 4.2）。代わりに次の 2 つを出し、人が目で見る材料にする。
- 走行ごとの基準を超えた 1 秒の数と、その割合が学習のとき（学習に使った窓の中での割合）と大きくずれないか
- 抜いた走行で付いたスコアの上位 N 件（走行・時刻・速度・rms・スコア・z_speed・判定）

学習に使った走行にそのまま点数を付ける今の処理（flow.py の retrain）とは分けて、ここだけで抜いて学習する。
どこにも書き込まない（モデルの版も、処理の記録も作らない）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import ANOMALY_NONE, anomaly_rule, apply_models, fit_models, judge_anomalies, training_mask

TOP_COLUMNS = ["ride_id", "t_rel", "speed_kmh", "rms", "score_if", "z_speed", "is_stopped", "is_anomaly_sif", "is_anomaly_z"]


@dataclass(frozen=True)
class Evaluation:
    method: str
    rides: pd.DataFrame  # 走行ごとの数
    top: pd.DataFrame    # 抜いた走行のスコアの上位 N 件（全走行をまとめて）


def leave_one_ride_out(windows: dict[str, pd.DataFrame], mcfg: dict, stop_speed_kmh: float = 5.0, top_n: int = 20) -> Evaluation:
    """windows は {走行 ID: その走行の窓}（学習に使う走行だけ）。走行の数だけ「抜いて学習 → 抜いた走行に点数」を繰り返す。

    判定の方法は mcfg の anomaly_method。割合の分母は GPS のある窓。学習のときの割合は、抜いて学習したモデルで、
    学習に使った窓（先頭・末尾・振り切れを除き、GPS のある窓）に点数を付けたときの割合。上位 N 件は走行中の窓から選ぶ。
    """
    if len(windows) < 2:
        raise ValueError("1 走行ずつ抜くには、学習に使う走行が 2 本以上要ります")
    rows, scored_all = [], []
    method = None
    for held_out in sorted(windows):
        rest = pd.concat([w for ride_id, w in windows.items() if ride_id != held_out], ignore_index=True)
        baseline, forest, info = fit_models(rest, mcfg)
        rule = anomaly_rule(mcfg, info)
        method = rule.method
        train = rest[training_mask(rest) & rest["has_gps"].fillna(False).astype(bool)]
        train_scored = apply_models(train, baseline, forest, mcfg, stop_speed_kmh, info)
        _, train_flag, _, _ = judge_anomalies(train_scored, rule)
        scored = apply_models(windows[held_out], baseline, forest, mcfg, stop_speed_kmh, info)
        judged_method, flag, score, threshold = judge_anomalies(scored, rule)
        n_gps = int(scored["has_gps"].fillna(False).sum())
        n_moving = int((scored["has_gps"].fillna(False) & ~scored["is_stopped"].fillna(False).astype(bool)).sum())
        rows.append({
            "ride_id": held_out,
            "n_windows": int(len(scored)),
            "n_gps": n_gps,
            "n_moving": n_moving,
            "max_speed_kmh": float(scored["speed_kmh"].max()) if n_gps else np.nan,
            "train_max_speed_kmh": float(rest.loc[rest["has_gps"].fillna(False).astype(bool), "speed_kmh"].max()),
            "threshold": np.nan if threshold is None else float(threshold),
            "n_over": 0 if judged_method == ANOMALY_NONE else int(flag.sum()),
            "rate_over": float(flag.sum() / n_gps) if n_gps else np.nan,
            "train_rate_over": float(train_flag.sum() / max(len(train_scored), 1)),
            "n_over_z": int(scored["is_anomaly_z"].fillna(False).sum()),
        })
        scored = scored.assign(ride_id=held_out, judged=flag, judge_score=score)
        # 上位は走行中の窓から選ぶ（どちらの方法も停止中は判定しない。停止中の z_speed は MAD が小さく針になる）
        moving = np.isfinite(scored["judge_score"].to_numpy(float)) & ~scored["is_stopped"].fillna(False).astype(bool).to_numpy()
        scored_all.append(scored[moving])
    pooled = pd.concat(scored_all, ignore_index=True) if scored_all else pd.DataFrame()
    top = pooled.sort_values("judge_score", ascending=False).head(top_n) if len(pooled) else pooled
    cols = [c for c in [*TOP_COLUMNS, "judge_score", "judged"] if c in top.columns]
    return Evaluation(method or "", pd.DataFrame(rows), top[cols].reset_index(drop=True))


def format_evaluation(result: Evaluation) -> str:
    """画面に出す文（Markdown の表）。"""
    lines = [f"判定の方法：{result.method}", "", "| 走行 | 1 秒の数 | GPS あり | 走行中 | 最高速度 | 学習の最高速度 | しきい値 | 基準を超えた数 | 割合 | 学習のときの割合 | z_speed で超えた数 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in result.rides.itertuples():
        lines.append(f"| {r.ride_id} | {r.n_windows} | {r.n_gps} | {r.n_moving} | {_num(r.max_speed_kmh, 1)} | {_num(r.train_max_speed_kmh, 1)} | {_num(r.threshold, 4)} | {r.n_over} | {_pct(r.rate_over)} | {_pct(r.train_rate_over)} | {r.n_over_z} |")
    lines += ["", f"抜いた走行のスコアの上位 {len(result.top)} 件", "", "| 順 | 走行 | 時刻（秒） | 速度 | rms | score_if | z_speed | 停止中 | 判定 |", "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(result.top.itertuples(), start=1):
        lines.append(f"| {i} | {r.ride_id} | {_num(r.t_rel, 1)} | {_num(r.speed_kmh, 1)} | {_num(r.rms, 3)} | {_num(r.score_if, 4)} | {_num(r.z_speed, 2)} | {'はい' if r.is_stopped else ''} | {'超えた' if r.judged else ''} |")
    return "\n".join(lines)


def _num(v, digits: int) -> str:
    return "—" if v is None or not np.isfinite(v) else f"{v:.{digits}f}"


def _pct(v) -> str:
    return "—" if v is None or not np.isfinite(v) else f"{v * 100:.2f}%"
