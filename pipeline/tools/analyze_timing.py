# -*- coding: utf-8 -*-
"""1セッションの時刻のなめらかさと、大きな揺れの時刻を調べる（データ仕様.md v2 の形式用）。

usage: python analyze_timing.py <ride_NNNフォルダー>

出すもの：
- t_us を サンプル番号 n の直線で近似したときの周期・周波数と、直線からのずれ（ADXL345 の内部クロックの揺らぎ）
- サンプル間隔のヒストグラム（500us 刻み。V2 は 2000/3000 に割れ、V2.1 は 2500 に集まる）
- 1秒窓ごとの合成加速度の標準偏差が大きい窓（叩いた・揺らした時刻）と、その日本時間（GPS の UTC から換算）
2026-11-02 に ride_019（バッテリー単体テスト）の解析に使ったもの。標準ライブラリだけで動く。
"""
import csv
import statistics
import sys
from collections import Counter


def main(d):
    n, t, mag = [], [], []
    with open(d + "/accel.csv", newline="") as f:
        for r in csv.DictReader(f):
            n.append(int(r["n"]))
            t.append(int(r["t_us"]))
            ax, ay, az = float(r["ax_g"]), float(r["ay_g"]), float(r["az_g"])
            mag.append((ax * ax + ay * ay + az * az) ** 0.5)
    N = len(n)
    mn, mt = sum(n) / N, sum(t) / N
    b = sum((x - mn) * (y - mt) for x, y in zip(n, t)) / sum((x - mn) ** 2 for x in n)
    a = mt - b * mn
    res = [y - (a + b * x) for x, y in zip(n, t)]
    print(f"直線近似: 周期 {b:.2f} us（{1e6 / b:.3f} Hz）、直線からのずれ 標準偏差 {statistics.pstdev(res) / 1000:.1f} ms、"
          f"最大 {max(abs(r) for r in res) / 1000:.1f} ms")
    dt = [y - x for x, y in zip(t, t[1:])]
    print("間隔のヒストグラム（500us刻み）:", sorted(Counter(round(x / 500) * 500 for x in dt).items())[:8])

    win = 400
    rows = []
    for i in range(0, N - win, win):
        w = mag[i:i + win]
        rows.append((statistics.pstdev(w), max(w) - min(w), t[i] / 1e6))
    print(f"1秒窓 {len(rows)} 個、標準偏差の中央値 {statistics.median(r[0] for r in rows) * 1000:.1f} mg")
    top = sorted(sorted(rows, reverse=True)[:8], key=lambda r: r[2])

    with open(d + "/gps.csv", newline="") as f:
        g = [r for r in csv.DictReader(f) if r["status"] == "A"]
    jst = None
    if g:
        u = g[0]["utc"]
        off = int(u[:2]) * 3600 + int(u[2:4]) * 60 + float(u[4:]) - int(g[0]["t_rx_us"]) / 1e6

        def jst(ts):
            s = (ts + off + 9 * 3600) % 86400
            return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:04.1f}"

        print("記録の開始・終了（日本時間）:", jst(t[0] / 1e6), "〜", jst(t[-1] / 1e6))
    for s, pp, ts in top:
        print(f"  揺れ t={ts:8.1f}s  標準偏差 {s * 1000:6.1f} mg  振れ幅 {pp:.3f} g" + (f"  日本時間 {jst(ts)}" if jst else ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1])
