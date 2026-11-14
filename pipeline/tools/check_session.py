# -*- coding: utf-8 -*-
"""SDカードの記録（/sessions/ride_NNN）を確認する。docs/data_spec_v2.md の形式用。

usage: python check_session.py <ride_NNNフォルダー> [...]
       python check_session.py <SD の sessions フォルダー>    （中のセッションを全部）

確認すること：記録時間、加速度の実測周波数、サンプル番号と時刻の飛び、
GPS の有効率と UTC 開始時刻、t_us と UTC の対応のばらつき、events.csv の件数。
標準ライブラリだけで動く。
"""
import csv
import os
import statistics
import sys
from collections import Counter


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def utc_seconds(utc):
    """hhmmss.sss → その日の0時からの秒"""
    if len(utc) < 6:
        return None
    return int(utc[0:2]) * 3600 + int(utc[2:4]) * 60 + float(utc[4:])


def check(d):
    name = os.path.basename(os.path.normpath(d))
    print(f"=== {name} ===")
    if not os.path.exists(os.path.join(d, "accel.csv")):
        print("  accel.csv がありません（V1 の記録か、記録が始まっていません）")
        return
    acc = read_csv(os.path.join(d, "accel.csv"))
    gps = read_csv(os.path.join(d, "gps.csv"))
    ev = read_csv(os.path.join(d, "events.csv"))

    # --- 加速度
    if len(acc) < 2:
        print(f"  加速度 {len(acc)} 行（記録がほとんどありません）")
    else:
        n = [int(r["n"]) for r in acc]
        t = [int(r["t_us"]) for r in acc]
        dur = (t[-1] - t[0]) / 1e6
        rate = (len(t) - 1) / dur if dur > 0 else 0
        dt = [b - a for a, b in zip(t, t[1:])]
        n_gaps = sum(1 for a, b in zip(n, n[1:]) if b != a + 1)
        big = sorted(dt)[-3:]
        print(f"  加速度: {len(acc)} 行 / {dur:.1f} 秒 / 実測 {rate:.2f} Hz")
        print(f"    間隔の中央値 {statistics.median(dt)} us、最小 {min(dt)} us、最大 {max(dt)} us（大きい順 {big[::-1]}）")
        spread = [x for x in dt if abs(x - statistics.median(dt)) > 100]
        print(f"    中央値から100us以上ずれた間隔 {len(spread)} か所（{100 * len(spread) / len(dt):.1f}%）"
              "　※V2 は丸めで約半分がずれる。V2.1 ならほぼ0")
        print(f"    サンプル番号の飛び {n_gaps} か所、時刻の逆転 {sum(1 for x in dt if x <= 0)} か所")
        mag = [(float(r['ax_g']) ** 2 + float(r['ay_g']) ** 2 + float(r['az_g']) ** 2) ** 0.5 for r in acc[:4000]]
        print(f"    最初の約10秒の合成加速度 平均 {statistics.mean(mag):.3f} g（静止なら約1g）")

    # --- GPS
    valid = [r for r in gps if r["status"] == "A"]
    print(f"  GPS: {len(gps)} 行、有効(A) {len(valid)} 行 ({100 * len(valid) / max(1, len(gps)):.0f}%)")
    if valid:
        first = valid[0]
        print(f"    最初の有効: date={first['date']} utc={first['utc']} sats={first['sats']} hdop={first['hdop']}")
        # t_rx_us と UTC の差（ずれのばらつき＝NMEA の遅れの揺れ）
        offs = []
        for r in valid:
            s = utc_seconds(r["utc"])
            if s is not None:
                offs.append(int(r["t_rx_us"]) / 1e6 - s)
        if len(offs) > 2:
            base = statistics.median(offs)
            dev = [abs(o - base) * 1000 for o in offs]
            print(f"    t_rx と UTC の差のばらつき: 中央値からの最大 {max(dev):.1f} ms、標準偏差 {statistics.pstdev(dev):.1f} ms")
        sp = [float(r["speed_kmh"]) for r in valid if r["speed_kmh"]]
        if sp:
            print(f"    速度: 最大 {max(sp):.1f} km/h、平均 {statistics.mean(sp):.1f} km/h")

    # --- events
    c = Counter(r["type"] for r in ev)
    print(f"  events: {dict(c)}")


def main():
    targets = []
    for a in sys.argv[1:]:
        if os.path.exists(os.path.join(a, "accel.csv")) or os.path.exists(os.path.join(a, "sensors.csv")):
            targets.append(a)
        elif os.path.isdir(a):
            targets += [os.path.join(a, x) for x in sorted(os.listdir(a)) if x.startswith("ride_")]
    if not targets:
        print(__doc__)
        return
    for d in targets:
        check(d)


if __name__ == "__main__":
    main()
