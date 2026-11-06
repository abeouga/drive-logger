# -*- coding: utf-8 -*-
"""静的 HTML の生成（計画書 10.）：folium の地図 ＋ Plotly のタイムラインを 1 ファイルに組み立てる。

- 軌跡は 1 秒窓ごとの線分、log_rms の 5 分位で 5 段階に色分け。
- is_anomaly_z の窓は赤丸、z_speed 上位 N 窓は橙丸（しきい値を超える窓がなくても見どころを示すため）。
- is_private の窓は線もマーカーも描かない。
- gps_fix_ratio が 10% 未満なら地図を描かず、注意書きとタイムラインだけ出す。部分欠損は線をつながない。
"""
from __future__ import annotations

import html
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .gps import haversine_m

QUINTILE_COLORS = ["#2c7bb6", "#abd9e9", "#ffffbf", "#fdae61", "#d7191c"]  # 青 → 黄 → 赤
MAP_MODES = ("none", "partial", "full")


# ------------------------------------------------------------------ 判定ロジック（テスト対象）
def gps_fix_ratio(df: pd.DataFrame) -> float:
    return float(df["has_gps"].mean()) if len(df) else 0.0


def map_mode(fix_ratio: float, min_ratio: float = 0.10, full_ratio: float = 0.95) -> str:
    """地図の描き方：none（描かない）／partial（fix のある窓だけ）／full。"""
    if fix_ratio < min_ratio:
        return "none"
    return "full" if fix_ratio >= full_ratio else "partial"


def quintile_classes(values: pd.Series) -> np.ndarray:
    """5 分位で 0〜4 のクラス。NaN は -1。値が少なく分位が重なるときは rank で割る。"""
    v = values.to_numpy(float)
    cls = np.full(len(v), -1)
    ok = np.isfinite(v)
    if ok.sum() == 0:
        return cls
    ranks = pd.Series(v[ok]).rank(method="first")
    cls[ok] = pd.qcut(ranks, 5, labels=False).to_numpy().astype(int) if ok.sum() >= 5 else np.clip(np.floor((ranks - 1) / max(ok.sum(), 1) * 5), 0, 4).astype(int)
    return cls


def ride_distance_km(df: pd.DataFrame) -> float:
    """has_gps の連続する窓の間の距離の合計 [km]（1 秒窓なので窓番号が連続しているときだけ足す）。"""
    g = df[df["has_gps"]].sort_values("win")
    if len(g) < 2:
        return 0.0
    consecutive = np.diff(g["win"].to_numpy()) == 1
    d = haversine_m(g["lat"].to_numpy()[:-1], g["lon"].to_numpy()[:-1], g["lat"].to_numpy()[1:], g["lon"].to_numpy()[1:])
    return float(np.nansum(d[consecutive]) / 1000)


def ride_summary(df: pd.DataFrame) -> dict:
    t_abs = df["t_abs"].dropna()
    return dict(
        ride_id=str(df["ride_id"].iloc[0]),
        start_jst=t_abs.iloc[0].strftime("%Y-%m-%d %H:%M") if len(t_abs) else None,
        duration_min=float(df["t_rel"].max() / 60),
        n_windows=int(len(df)),
        fix_ratio=gps_fix_ratio(df),
        distance_km=ride_distance_km(df),
        n_anom_z=int(df.get("is_anomaly_z", pd.Series(False, index=df.index)).sum()),
        n_anom_if=int(df.get("is_anomaly_if", pd.Series(False, index=df.index)).sum()),
        z_max=float(df["z_speed"].max()) if "z_speed" in df and df["z_speed"].notna().any() else None,
        n_private=int(df["is_private"].sum()),
        n_clipped=int(df["is_clipped"].sum()),
    )


# ------------------------------------------------------------------ 地図
def _popup(row: pd.Series) -> str:
    t = row["t_abs"].strftime("%H:%M:%S") if pd.notna(row["t_abs"]) else f"{row['t_rel']:.0f} s"
    return (
        f"<b>{html.escape(str(row['ride_id']))}</b> {t} JST<br>"
        f"速度 {row['speed_kmh']:.1f} km/h<br>rms {row['rms']:.2f} g<br>"
        f"z_speed {row['z_speed']:.2f}<br>score_if {row['score_if']:.3f}"
    )


def build_map(df: pd.DataFrame, mode: str, top_n: int = 10) -> folium.Map | None:
    if mode == "none":
        return None
    d = df[df["has_gps"] & ~df["is_private"]].sort_values("win").copy()
    if len(d) < 2:
        return None
    m = folium.Map(location=[float(d["lat"].mean()), float(d["lon"].mean())], zoom_start=15, tiles="OpenStreetMap", control_scale=True)
    d["cls"] = quintile_classes(d["log_rms"])
    lat = d["lat"].to_numpy()
    lon = d["lon"].to_numpy()
    win = d["win"].to_numpy()
    cls = d["cls"].to_numpy()
    for i in range(len(d) - 1):
        if win[i + 1] - win[i] != 1:  # 欠損・マスクの区間は線をつながない
            continue
        c = QUINTILE_COLORS[max(cls[i], cls[i + 1], 0)]
        folium.PolyLine([(lat[i], lon[i]), (lat[i + 1], lon[i + 1])], color=c, weight=5, opacity=0.9).add_to(m)
    # マーカー：しきい値超え（赤）、上位 N（橙）
    top = d[d["z_speed"].notna()].nlargest(top_n, "z_speed")
    for _, r in top.iterrows():
        if not r["is_anomaly_z"]:
            folium.CircleMarker((r["lat"], r["lon"]), radius=6, color="#e6811c", fill=True, fill_opacity=0.9, popup=folium.Popup(_popup(r), max_width=260)).add_to(m)
    for _, r in d[d["is_anomaly_z"]].iterrows():
        folium.CircleMarker((r["lat"], r["lon"]), radius=7, color="#c00000", fill=True, fill_opacity=0.9, popup=folium.Popup(_popup(r), max_width=260)).add_to(m)
    legend = (
        '<div style="position:fixed;bottom:30px;left:30px;z-index:9999;background:white;padding:8px 10px;border:1px solid #999;font-size:12px;line-height:1.6">'
        "<b>log_rms の 5 分位</b><br>"
        + "".join(f'<span style="display:inline-block;width:14px;height:10px;background:{c};margin-right:4px"></span>{lab}<br>' for c, lab in zip(QUINTILE_COLORS, ["0–20%（静か）", "20–40%", "40–60%", "60–80%", "80–100%（大）"]))
        + '<span style="color:#c00000">●</span> z_speed &gt; 3　<span style="color:#e6811c">●</span> z_speed 上位 10 窓'
        "</div>"
    )
    m.get_root().html.add_child(folium.Element(legend))
    return m


# ------------------------------------------------------------------ タイムライン
def build_timeline(df: pd.DataFrame, z_threshold: float = 3.0) -> go.Figure:
    d = df.sort_values("win")
    use_abs = d["t_abs"].notna().any()
    x = d["t_abs"] if use_abs else d["t_rel"]
    xlabel = "時刻（JST）" if use_abs else "走行開始からの秒（GPS がないので絶対時刻なし）"
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35], vertical_spacing=0.06, specs=[[{"secondary_y": True}], [{}]])
    fig.add_trace(go.Scatter(x=x, y=d["rms"], name="rms [g]", line=dict(color="#1f4e79", width=1.2)), row=1, col=1, secondary_y=False)
    if d["has_gps"].any():
        fig.add_trace(go.Scatter(x=x, y=d["speed_kmh"], name="速度 [km/h]", line=dict(color="#2e8b57", width=1), opacity=0.8), row=1, col=1, secondary_y=True)
    has_z = "z_speed" in d and d["z_speed"].notna().any()
    if has_z:
        fig.add_trace(go.Scatter(x=x, y=d["z_speed"], name="z_speed", line=dict(color="#c00000", width=1)), row=2, col=1)
        fig.add_hline(y=z_threshold, line=dict(color="#c00000", dash="dot", width=1), row=2, col=1)
    if "score_if" in d:
        # z_speed がない走行（GPS なし）では score_if を下段に出す。ある走行では凡例から切り替え
        fig.add_trace(go.Scatter(x=x, y=d["score_if"], name="score_if（Isolation Forest）", line=dict(color="#7f7f7f", width=1, dash="dot"), visible="legendonly" if has_z else True), row=2, col=1)
    # 帯：異常窓（赤）、GPS なし（灰）、先頭末尾（薄灰）
    for flag, color, name in [("is_anomaly_z", "rgba(192,0,0,0.25)", "z>3"), ("is_edge", "rgba(128,128,128,0.10)", "先頭・末尾 60 秒")]:
        if flag in d and d[flag].any():
            _add_bands(fig, x, d[flag].to_numpy(), color, name)
    if d["has_gps"].any() and (~d["has_gps"]).any():
        _add_bands(fig, x, (~d["has_gps"]).to_numpy(), "rgba(255,140,0,0.12)", "GPS なし")
    fig.update_yaxes(title_text="rms [g]", row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="km/h", row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="z_speed" if has_z else "score_if", row=2, col=1)
    fig.update_xaxes(title_text=xlabel, row=2, col=1)
    fig.update_layout(height=520, margin=dict(l=50, r=30, t=30, b=40), legend=dict(orientation="h", y=1.08), hovermode="x unified")
    return fig


def _add_bands(fig: go.Figure, x: pd.Series, flag: np.ndarray, color: str, name: str) -> None:
    """連続する True の区間ごとに縦の帯を 1 つ描く（窓が多くても形が増えすぎないように）。"""
    xv = x.to_numpy()
    starts = np.where(flag & ~np.r_[False, flag[:-1]])[0]
    ends = np.where(flag & ~np.r_[flag[1:], False])[0]
    for i, (s, e) in enumerate(zip(starts, ends)):
        x0, x1 = xv[s], xv[min(e + 1, len(xv) - 1)]
        extra = dict(annotation_text=name, annotation_position="top left", annotation_font_size=10) if i == 0 else {}
        fig.add_vrect(x0=x0, x1=x1, fillcolor=color, line_width=0, layer="below", **extra)


# ------------------------------------------------------------------ ページ組み立て
NOTE_NONE = "この走行は GPS が捕捉できなかったため地図は表示していません。タイムラインのみ表示します（横軸は走行開始からの秒）。"
NOTE_PARTIAL = "GPS が途切れた区間は地図に描いていません（タイムラインの橙の帯）。"
NOTE_PRIVATE = "自宅など登録地点の周辺 {r} m の窓は地図に描いていません。"
NOTE_NO_MASK = "注意：config/local.yaml がないため自宅周辺のマスクは未適用です。この HTML を公開・アップロードしないでください。"
FOOTER = (
    "異常スコアは、健康な車両の走行データから作った「速度で補正した正常時のベースライン」からの逸脱です。"
    "故障データは含まれておらず、スコアが高い窓は「路面または車両に起因する振動の変化」を示すもので、車両の異常と断定するものではありません。"
)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:"Segoe UI","Yu Gothic UI",Meiryo,sans-serif;margin:0;background:#f6f7f9;color:#222}}
header{{background:#1f4e79;color:#fff;padding:14px 20px}} header h1{{font-size:20px;margin:0}} header a{{color:#cfe2ff}}
main{{max-width:1200px;margin:0 auto;padding:16px 20px}} .card{{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px 16px;margin-bottom:16px}}
.note{{background:#fff4e5;border-left:4px solid #e6811c;padding:8px 12px;margin:8px 0}} .warn{{background:#fde8e8;border-left:4px solid #c00000;padding:8px 12px;margin:8px 0}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #e3e3e3;padding:6px 8px;text-align:left;font-size:14px}} th{{background:#f0f3f7}}
.kv span{{display:inline-block;margin-right:18px;font-size:14px}} footer{{font-size:12px;color:#555;padding:12px 20px}}
</style></head><body>{body}<footer>{FOOTER}</footer></body></html>"""


def render_ride_html(df: pd.DataFrame, cfg: dict) -> str:
    vcfg = cfg.get("viz", {})
    s = ride_summary(df)
    mode = map_mode(s["fix_ratio"], vcfg.get("map_min_fix_ratio", 0.10), vcfg.get("map_full_fix_ratio", 0.95))
    fig = build_timeline(df, cfg.get("model", {}).get("z_threshold", 3.0))
    m = build_map(df, mode, vcfg.get("top_n_markers", 10))
    has_mask = bool((cfg.get("local") or {}).get("home")) or bool((cfg.get("local") or {}).get("places"))

    notes = []
    if mode == "none":
        notes.append(f'<div class="note">{NOTE_NONE}</div>')
    elif mode == "partial":
        notes.append(f'<div class="note">{NOTE_PARTIAL}</div>')
    if mode != "none":
        notes.append(f'<div class="note">{NOTE_PRIVATE.format(r=cfg.get("private_radius_m", 300))}</div>' if has_mask else f'<div class="warn">{NOTE_NO_MASK}</div>')
    kv = (
        f'<div class="kv"><span>開始 {s["start_jst"] or "不明（GPS なし）"}</span><span>記録 {s["duration_min"]:.1f} 分</span>'
        f'<span>距離 {s["distance_km"]:.1f} km</span><span>GPS 有効 {s["fix_ratio"]:.0%}</span>'
        f'<span>窓 {s["n_windows"]}</span><span>z_speed &gt; 3：{s["n_anom_z"]} 窓</span><span>Isolation Forest：{s["n_anom_if"]} 窓</span>'
        f'<span>振り切れ {s["n_clipped"]} 窓</span></div>'
    )
    map_html = m._repr_html_() if m is not None else ""
    body = (
        f'<header><h1>{html.escape(s["ride_id"])}　走行の振動マップとタイムライン</h1><a href="../index.html">← 走行一覧</a></header><main>'
        f'<div class="card">{kv}{"".join(notes)}</div>'
        + (f'<div class="card"><h2 style="font-size:16px;margin:0 0 8px">地図（線の色＝log_rms の 5 分位、赤丸＝z_speed &gt; 3、橙丸＝z_speed 上位 10 窓）</h2>{map_html}</div>' if map_html else "")
        + f'<div class="card"><h2 style="font-size:16px;margin:0 0 8px">タイムライン（上：rms と速度、下：z_speed。赤帯＝z &gt; 3、橙帯＝GPS なし）</h2>'
        + fig.to_html(full_html=False, include_plotlyjs="cdn")
        + "</div></main>"
    )
    return _page(f"{s['ride_id']} CT125 振動マップ", body)


def render_index_html(summaries: list[dict], cfg: dict) -> str:
    rows = "".join(
        f'<tr><td><a href="{html.escape(s["ride_id"])}/index.html">{html.escape(s["ride_id"])}</a></td><td>{s["start_jst"] or "不明"}</td>'
        f'<td>{s["duration_min"]:.1f}</td><td>{s["distance_km"]:.1f}</td><td>{s["fix_ratio"]:.0%}{"（地図なし）" if map_mode(s["fix_ratio"], cfg.get("viz", {}).get("map_min_fix_ratio", 0.10)) == "none" else ""}</td>'
        f'<td>{s["n_anom_z"]}</td><td>{s["n_anom_if"]}</td><td>{"" if s["z_max"] is None else f"{s["z_max"]:.2f}"}</td><td>{html.escape(s.get("memo", ""))}</td></tr>'
        for s in summaries
    )
    body = (
        '<header><h1>CT125 走行データロガー　走行一覧</h1></header><main><div class="card">'
        "<p>ESP32 ＋ GPS ＋ 加速度センサーで記録した走行ごとに、1 秒窓の振動を地図とタイムラインで表示します。GPS が取れなかった走行はタイムラインのみです。</p>"
        "<table><thead><tr><th>走行</th><th>開始（JST）</th><th>分</th><th>距離 km</th><th>GPS 有効</th><th>z_speed &gt; 3</th><th>Isolation Forest</th><th>z_speed 最大</th><th>メモ</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></main>"
    )
    return _page("CT125 走行一覧", body)


def render_all(processed_dir: Path, web_dir: Path, cfg: dict, memos: dict[str, str] | None = None, rides: list[str] | None = None, verbose: bool = True) -> list[dict]:
    paths = sorted(processed_dir.glob("ride_*/scored.parquet"))
    if rides:
        paths = [p for p in paths if p.parent.name in rides]
    if not paths:
        raise FileNotFoundError("scored.parquet がありません。先に process と score を実行してください")
    summaries = []
    for p in paths:
        df = pd.read_parquet(p)
        rid = p.parent.name
        (web_dir / rid).mkdir(parents=True, exist_ok=True)
        (web_dir / rid / "index.html").write_text(render_ride_html(df, cfg), encoding="utf-8")
        s = ride_summary(df)
        s["memo"] = (memos or {}).get(rid, "")
        summaries.append(s)
        if verbose:
            print(f"{rid}: 地図 {map_mode(s['fix_ratio'])}, GPS 有効 {s['fix_ratio']:.0%}, 距離 {s['distance_km']:.1f} km, z>3 {s['n_anom_z']}, IF {s['n_anom_if']} → {web_dir / rid / 'index.html'}")
    # 一覧は web/ 配下の全走行で作る（今回絞って描いた分だけでなく）
    all_summ = summaries
    if rides:
        all_summ = []
        for p in sorted(processed_dir.glob("ride_*/scored.parquet")):
            s = ride_summary(pd.read_parquet(p))
            s["memo"] = (memos or {}).get(p.parent.name, "")
            all_summ.append(s)
    (web_dir / "index.html").write_text(render_index_html(all_summ, cfg), encoding="utf-8")
    return summaries
