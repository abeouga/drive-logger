# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import pytest

from ct125 import model


def _windows(n_per_bin=50, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for b, med in [(0, -2.0), (1, -1.0), (2, 0.0)]:        # 0-5, 5-10, 10-15 km/h で log_rms の中央値が上がる
        spd = rng.uniform(b * 5, b * 5 + 5, n_per_bin)
        x = med + rng.normal(0, 0.1, n_per_bin)
        rows.append(pd.DataFrame({"speed_kmh": spd, "log_rms": x, "has_gps": True}))
    return pd.concat(rows, ignore_index=True)


def test_speed_baseline_medians_and_z():
    df = _windows()
    bl = model.fit_speed_baseline(df, bin_kmh=5.0, min_count=10)
    meds = [b["median"] for b in bl["bins"]]
    assert meds == pytest.approx([-2.0, -1.0, 0.0], abs=0.05)
    # 速度 7 km/h で log_rms が中央値ちょうどなら z≈0、中央値＋大きな正ならビン幅に応じて z が大きい
    q = pd.DataFrame({"speed_kmh": [7.0, 7.0, np.nan], "log_rms": [-1.0, 1.0, 0.0]})
    z = model.apply_speed_baseline(q, bl)
    assert abs(z.iloc[0]) < 0.5
    assert z.iloc[1] > 3
    assert np.isnan(z.iloc[2])          # 速度がない窓は NaN


def test_speed_baseline_sparse_bin_borrows_neighbor():
    df = _windows()
    # 15-20 km/h に 2 窓だけ足す → min_count 未満なので最寄り（10-15）の値を借りる
    extra = pd.DataFrame({"speed_kmh": [17.0, 18.0], "log_rms": [5.0, 5.0], "has_gps": True})
    bl = model.fit_speed_baseline(pd.concat([df, extra], ignore_index=True), 5.0, 10)
    b3 = bl["bins"][3]
    assert b3["n"] == 2 and b3["source_bin"] == 2 and b3["median"] == pytest.approx(0.0, abs=0.05)


def test_isolation_forest_flags_outlier():
    rng = np.random.default_rng(1)
    n = 500
    df = pd.DataFrame({c: rng.normal(0, 1, n) for c in model.IF_FEATURES})
    df.loc[0, model.IF_FEATURES] = 8.0      # 明らかな外れ値
    forest = model.fit_isolation_forest(df, contamination=0.03, n_estimators=100)
    s = model.apply_isolation_forest(df, forest)
    assert s["score_if"].iloc[0] == s["score_if"].max()
    assert bool(s["is_anomaly_if"].iloc[0])
    assert 0.0 < s["is_anomaly_if"].mean() < 0.1


def test_saved_forest_gives_the_same_scores_after_loading(tmp_path):
    rng = np.random.default_rng(2)
    df = pd.DataFrame({c: rng.normal(0, 1, 300) for c in model.IF_FEATURES})
    forest = model.fit_isolation_forest(df, n_estimators=50)
    path = tmp_path / "isolation_forest.skops"
    model.save_model(forest, path)
    assert not path.read_bytes().startswith(b"\x80")      # pickle の先頭（protocol 2 以上）ではない
    pd.testing.assert_frame_equal(model.apply_isolation_forest(df, model.load_model(path)), model.apply_isolation_forest(df, forest))


def test_forest_file_with_untrusted_types_is_refused():
    from skops.io.exceptions import UntrustedTypesFoundException

    with pytest.raises(UntrustedTypesFoundException):
        model.load_forest(skops_dumps({"f": len}))     # 信頼する型の外（builtins.len）


def test_forest_trusted_types_are_exactly_what_skops_reports():
    import skops.io as sio

    df = pd.DataFrame({c: np.arange(50, dtype=float) for c in model.IF_FEATURES})
    data = model.dump_forest(model.fit_isolation_forest(df, n_estimators=5))
    assert sorted(sio.get_untrusted_types(data=data)) == sorted(model.FOREST_TRUSTED_TYPES)


def skops_dumps(obj) -> bytes:
    import skops.io as sio

    return sio.dumps(obj)


# ------------------------------------------------------------------ 速度を足した Isolation Forest（#81）
MCFG = {"contamination": 0.03, "n_estimators": 100, "random_state": 0, "anomaly_quantile": 0.99, "z_threshold": 3.0}


def _rides(n=600, seed=0):
    """速度が上がるほど振動が大きくなる走行。速度は 5〜60 km/h（走行中）。"""
    rng = np.random.default_rng(seed)
    speed = rng.uniform(5, 60, n)
    frame = pd.DataFrame({"speed_kmh": speed, "has_gps": True, "is_edge": False, "is_clipped": False})
    frame["log_rms"] = -2 + speed / 20 + rng.normal(0, 0.1, n)
    for name in model.VIBRATION_FEATURES:
        if name != "log_rms":
            frame[name] = frame["log_rms"] * 0.5 + rng.normal(0, 0.1, n)
    return frame


def _probe(speed_kmh: float, shift: float) -> pd.DataFrame:
    """その速度でのふだんの振動から shift だけずらした 1 秒。"""
    log_rms = -2 + speed_kmh / 20 + shift
    row = {"speed_kmh": speed_kmh, "has_gps": True, "is_edge": False, "is_clipped": False, "log_rms": log_rms}
    row.update({name: log_rms * 0.5 for name in model.VIBRATION_FEATURES if name != "log_rms"})
    return pd.DataFrame([row])


def test_speed_is_a_feature_and_threshold_is_the_training_quantile():
    train = _rides()
    baseline, forest, info = model.fit_models(train, MCFG)
    assert info["features"] == model.IF_FEATURES and "speed_kmh" in info["features"]
    assert forest.n_features_in_ == len(model.IF_FEATURES)
    scores = model.apply_isolation_forest(train, forest)["score_if"]
    assert info["threshold"] == pytest.approx(float(np.quantile(scores, 0.99)))
    assert info["quantile"] == 0.99 and info["n_train"] == len(train)


def test_too_quiet_window_is_not_judged_even_with_a_high_score():
    """振動が小さすぎる 1 秒は、Isolation Forest のスコアがしきい値を超えても判定に入らない。"""
    baseline, forest, info = model.fit_models(_rides(), MCFG)
    probes = pd.concat([_probe(40, -3.0), _probe(40, +3.0)], ignore_index=True)  # 静かすぎる・大きすぎる
    scored = model.apply_models(probes, baseline, forest, MCFG, forest_info=info)
    assert (scored["score_if"] > info["threshold"]).all()       # どちらもまれな組み合わせ
    assert scored["is_anomaly_sif"].tolist() == [False, True]   # 判定は大きい側だけ


def test_fast_but_ordinary_window_is_not_judged():
    """速く走って振動が大きいだけ（その速度ではふだんどおり）の 1 秒は、判定に入らない。"""
    baseline, forest, info = model.fit_models(_rides(), MCFG)
    scored = model.apply_models(_probe(55, 0.0), baseline, forest, MCFG, forest_info=info)
    assert not scored["is_anomaly_sif"].any()


def test_stopped_and_no_gps_windows_are_not_judged():
    train = _rides()
    no_gps = train.assign(has_gps=False, speed_kmh=np.nan).head(50)
    baseline, forest, info = model.fit_models(pd.concat([train, no_gps], ignore_index=True), MCFG)
    assert info["n_train"] == len(train)                         # GPS の無い 1 秒は学習に使わない
    stopped = _probe(2, +3.0)
    scored = model.apply_models(pd.concat([stopped, no_gps.head(3)], ignore_index=True), baseline, forest, MCFG, forest_info=info)
    assert scored["score_if"].iloc[1:].isna().all()              # 速度が無ければスコアも付けない
    assert not scored["is_anomaly_sif"].any()


def test_judge_switches_by_rule():
    baseline, forest, info = model.fit_models(_rides(), MCFG)
    scored = model.apply_models(pd.concat([_probe(40, 0.0), _probe(40, +3.0)], ignore_index=True), baseline, forest, MCFG, forest_info=info)
    method, flag, score, threshold = model.judge_anomalies(scored, model.anomaly_rule({**MCFG, "anomaly_method": "speed_iforest"}, info))
    assert method == "speed_iforest" and threshold == info["threshold"]
    assert flag.tolist() == [False, True] and np.allclose(score, scored["score_if"])
    method, flag, score, threshold = model.judge_anomalies(scored, model.anomaly_rule(MCFG, info))
    assert method == "speed_baseline" and threshold == 3.0 and np.allclose(score, scored["z_speed"])


def test_speed_iforest_needs_a_model_with_a_threshold():
    with pytest.raises(ValueError, match="学習し直して"):
        model.anomaly_rule({"anomaly_method": "speed_iforest"}, None)
    with pytest.raises(ValueError, match="anomaly_method"):
        model.anomaly_rule({"anomaly_method": "top_n"}, None)
    with pytest.raises(ValueError, match="anomaly_quantile"):
        model.forest_threshold(np.arange(10.0), 1.0)


def test_legacy_forest_without_speed_still_scores():
    """速度を足す前の版（振動の特徴量だけ）も読める。is_anomaly_sif は立たない。"""
    train = _rides()
    baseline = model.fit_speed_baseline(train)
    forest = model.fit_isolation_forest(train, n_estimators=50, features=model.VIBRATION_FEATURES)
    scored = model.apply_models(train.head(10), baseline, forest, MCFG)
    assert scored["score_if"].notna().all() and not scored["is_anomaly_sif"].any()
