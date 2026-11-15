# -*- coding: utf-8 -*-
"""スペクトログラムと生波形の書き出し。"""
import struct
import zlib

import numpy as np
import pandas as pd
import pytest

from ct125 import spectro

FS = 398.5


def _acc(seconds=4, freq=24.0, amp=0.5):
    n = int(FS * seconds)
    t = np.arange(n) / FS
    return pd.DataFrame({"t_rel": t, "ax_g": 0.1 + amp * np.sin(2 * np.pi * freq * t), "ay_g": 0.95, "az_g": -0.3})


def test_peak_frequency_matches_input():
    # アイドリング相当の 24 Hz が、2 倍（48 Hz）ではなく 24 Hz の行に出ること
    p = spectro.spectrogram(_acc(), np.array([0.0, 1.0, 2.0]), FS)
    assert p.shape == (3, spectro.F_MAX_HZ)
    assert all(int(np.nanargmax(row)) == 24 for row in p)


def test_alpha_image_orientation_and_levels():
    p = spectro.spectrogram(_acc(freq=50.0), np.array([0.0, 1.0]), FS)
    img, meta = spectro.to_alpha(p)
    assert img.shape == (spectro.F_MAX_HZ, 2)                 # 行＝周波数、列＝窓
    assert img.dtype == np.uint8
    row_50 = spectro.F_MAX_HZ - 1 - 50                        # 上が高い周波数
    assert img[row_50].min() == 255
    assert img[-1].max() == 0                                 # DC は描かない
    assert len(np.unique(img)) <= spectro.ALPHA_LEVELS
    assert meta["db_max"] > meta["db_min"]


def test_png_is_valid(tmp_path):
    alpha = np.array([[0, 128, 255], [255, 0, 17]], dtype=np.uint8)
    path = tmp_path / "s.png"
    spectro.write_png_alpha(path, alpha)
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    assert (w, h, depth, ctype) == (3, 2, 8, 4)               # 8 bit、グレー＋アルファ
    # IDAT を戻して、アルファの値がそのまま入っていること
    idat_len = struct.unpack(">I", data[33:37])[0]
    raw = zlib.decompress(data[41:41 + idat_len])
    rows = [raw[i * 7 + 1:(i + 1) * 7] for i in range(2)]
    assert [list(r[1::2]) for r in rows] == alpha.tolist()


def test_waveforms_are_demeaned_mg():
    acc = _acc(seconds=3, freq=10.0, amp=0.2)
    w = spectro.waveforms(acc, np.array([0.0, 1.0, 2.0]), [1], FS)
    assert len(w) == 1 and w[0]["i"] == 1 and w[0]["t0"] == pytest.approx(1.0)
    ax = np.array(w[0]["ax"])
    assert abs(ax.mean()) < 5                                 # 平均を引いてある（mg）
    assert ax.max() == pytest.approx(200, abs=5)              # 振幅 0.2 g = 200 mg
    assert set(w[0]["ay"]) == {0}                             # 一定の軸は 0


# ------------------------------------------------------------------ 800 Hz の走行（#112）
FS_800 = 797.0


def _acc800(seconds=3, freq=300.0, amp=0.5):
    n = int(FS_800 * seconds)
    t = np.arange(n) / FS_800
    return pd.DataFrame({"t_rel": t, "ax_g": 0.1 + amp * np.sin(2 * np.pi * freq * t), "ay_g": 0.95, "az_g": -0.3})


def test_f_max_follows_fs():
    assert spectro.f_max_for(398.5) == spectro.F_MAX_HZ == 200   # 400 Hz の走行は今のまま
    assert spectro.f_max_for(797.0) == 400
    assert spectro.f_max_for(float("nan")) == spectro.F_MAX_HZ


def test_800hz_draws_up_to_400hz():
    # 200 Hz より上（300 Hz）が、その行に出ること
    p = spectro.spectrogram(_acc800(), np.array([0.0, 1.0]), FS_800)
    assert p.shape == (2, 400)
    assert all(int(np.nanargmax(row)) == 300 for row in p)


def test_800hz_uses_the_whole_window():
    # 1 秒窓の後半だけに振動がある。窓の全部のサンプルを使っていれば、その周波数に出る
    acc = _acc800(seconds=1, freq=120.0)
    half = acc["t_rel"] < 0.5
    acc.loc[half, "ax_g"] = 0.1
    p = spectro.spectrogram(acc, np.array([0.0]), FS_800)
    assert int(np.nanargmax(p[0][5:])) + 5 == 120
