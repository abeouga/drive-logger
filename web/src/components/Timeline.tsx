// タイムライン（ECharts）。横軸を共有する段を縦に並べる（2 本の縦軸は使わない）。
//   GPS あり：rms（対数軸）／速度／z_speed
//   GPS なし：rms（対数軸）／score_if
// - カーソル → onHover（地図に点）、クリック → onSelect、範囲の拡大 → onRange（地図がその区間に寄る）
// - 地図側のカーソル（hover）と選択（selected）を縦線で示す
import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, MarkLineComponent, MarkPointComponent, AxisPointerComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { RideData } from "../lib/data";
import { fmtElapsed, fmtTimeSec } from "../lib/format";
import { nearestIndex, runs, xValues, zThreshold, type Selection } from "../lib/series";
import { cssVar } from "../lib/theme";

echarts.use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent, MarkLineComponent, MarkPointComponent, AxisPointerComponent, CanvasRenderer]);

interface Props {
  data: RideData;
  hover: Selection;
  selected: Selection;
  ranked: number[];
  onHover: (i: Selection) => void;
  onSelect: (i: Selection) => void;
  onRange: (r: [number, number] | null) => void;
}

interface Panel {
  key: string;
  name: string;
  unit: string;
  values: (number | null)[];
  log?: boolean;
  threshold?: number;
  digits: number;
}

export default function Timeline({ data, hover, selected, ranked, onHover, onSelect, onRange }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const cb = useRef({ onHover, onSelect, onRange });
  cb.current = { onHover, onSelect, onRange };
  const xs = useMemo(() => xValues(data), [data]);
  const abs = data.has_abs_time;
  const gps = data.columns.has_gps.some(Boolean);

  const panels: Panel[] = useMemo(() => {
    const c = data.columns;
    const p: Panel[] = [{ key: "rms", name: "振動 rms", unit: "g", values: c.rms.map((v) => (v !== null && v > 0 ? v : null)), log: true, digits: 3 }];
    if (gps) {
      p.push({ key: "speed", name: "速度", unit: "km/h", values: c.speed, digits: 1 });
      // 停止中（5 km/h 未満）はアイドリングの窓ばかりで MAD が極端に小さく、z が ±20 を超える針になる。
      // 基準を超えた振動の判定と同じく、走行中の窓だけを描く。しきい値の線は画面用データの値を使う
      p.push({ key: "z", name: "z_speed（走行中のみ）", unit: "", values: c.z.map((v, i) => (c.is_stopped[i] ? null : v)), threshold: zThreshold(data), digits: 2 });
    } else {
      p.push({ key: "score_if", name: "score_if（Isolation Forest）", unit: "", values: c.score_if, digits: 3 });
    }
    return p;
  }, [data, gps]);

  const fmtX = (v: number) => (abs ? fmtTimeSec(v) : fmtElapsed(v));

  // グラフを作る（走行・明暗が変わったら作り直す）
  useEffect(() => {
    if (!box.current) return;
    const ink = cssVar("--ink"), ink2 = cssVar("--ink-2"), muted = cssVar("--muted"), grid = cssVar("--grid"), axis = cssVar("--axis");
    const accent = cssVar("--accent"), surface = cssVar("--surface");
    const c = echarts.init(box.current, undefined, { renderer: "canvas" });
    chart.current = c;

    const n = panels.length;
    const top = 28, gap = 34, bottom = 56;
    const h = box.current.clientHeight;
    const ph = (h - top - bottom - gap * (n - 1)) / n;
    const stopped = runs(data.columns.is_stopped);
    const noGps = gps ? runs(data.columns.has_gps.map((v) => !v)) : [];
    const area = (r: [number, number][], color: string) =>
      r.map(([a, b]) => [{ xAxis: xs[a], itemStyle: { color } }, { xAxis: xs[Math.min(b + 1, xs.length - 1)] }]);

    c.setOption({
      animation: false,
      textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: ink2 },
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: muted }, label: { backgroundColor: ink, color: surface } },
      tooltip: {
        trigger: "axis",
        backgroundColor: surface,
        borderColor: grid,
        textStyle: { color: ink, fontSize: 12 },
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0]?.dataIndex;
          if (i === undefined) return "";
          const rows = panels
            .map((p) => {
              const v = p.values[i];
              return `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${ink2}">${p.name}</span><b style="font-variant-numeric:tabular-nums">${v === null ? "—" : v.toFixed(p.digits)} ${p.unit}</b></div>`;
            })
            .join("");
          return `<div style="font-variant-numeric:tabular-nums;margin-bottom:4px">${fmtX(xs[i])}</div>${rows}`;
        },
      },
      grid: panels.map((_, k) => ({ left: 56, right: 16, top: top + k * (ph + gap), height: ph })),
      xAxis: panels.map((_, k) => ({
        gridIndex: k,
        type: abs ? "time" : "value",
        min: xs[0],
        max: xs[xs.length - 1],
        axisLine: { lineStyle: { color: axis } },
        axisTick: { show: false },
        axisLabel: { show: k === n - 1, color: muted, formatter: (v: number) => fmtX(v), hideOverlap: true },
        splitLine: { show: false },
      })),
      yAxis: panels.map((p, k) => ({
        gridIndex: k,
        type: p.log ? "log" : "value",
        name: p.unit ? `${p.name}（${p.unit}）` : p.name,
        nameLocation: "end",
        nameGap: 8,
        nameTextStyle: { color: ink2, align: "left", fontSize: 12 },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { lineStyle: { color: grid } },
        splitNumber: 3,
        scale: !p.log,
      })),
      dataZoom: [
        { type: "inside", xAxisIndex: panels.map((_, k) => k), filterMode: "none" },
        { type: "slider", xAxisIndex: panels.map((_, k) => k), filterMode: "none", height: 18, bottom: 8, borderColor: grid, labelFormatter: (v: number) => fmtX(v), textStyle: { color: muted } },
      ],
      series: panels.map((p, k) => ({
        id: p.key,
        name: p.name,
        type: "line",
        xAxisIndex: k,
        yAxisIndex: k,
        data: p.values.map((v, i) => [xs[i], v]),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.5, color: accent },
        itemStyle: { color: accent },
        emphasis: { disabled: true },
        // 背景の帯：停止中（灰）、GPS なし（薄い斜線の代わりに薄い灰）。最上段だけに凡例の文字を出す
        markArea: {
          silent: true,
          label: { show: false },
          data: [...area(stopped, "rgba(137,135,129,0.12)"), ...area(noGps, "rgba(137,135,129,0.22)")],
        },
        markLine: p.threshold !== undefined
          ? { silent: true, symbol: "none", lineStyle: { color: muted, type: "dashed" }, label: { formatter: `${p.threshold}`, color: muted }, data: [{ yAxis: p.threshold }] }
          : undefined,
        // 基準を超えた振動の番号（最上段の rms の上。地図・一覧と同じ番号）
        markPoint: k === 0
          ? {
              symbol: "circle",
              symbolSize: 16,
              itemStyle: { color: ink, borderColor: surface, borderWidth: 2 },
              label: { color: surface, fontSize: 9, formatter: (q: { name: string }) => q.name },
              data: ranked.map((i, r) => ({ name: String(r + 1), coord: [xs[i], panels[0].values[i]] })),
            }
          : undefined,
      })),
    });

    // カーソル → 地図
    c.on("updateAxisPointer", (e: unknown) => {
      const info = (e as { axesInfo?: { value: number }[] }).axesInfo?.[0];
      cb.current.onHover(info ? nearestIndex(xs, info.value) : null);
    });
    c.getZr().on("mouseout", () => cb.current.onHover(null));
    // クリック → 選択
    c.getZr().on("click", (ev: { offsetX: number; offsetY: number }) => {
      for (let k = 0; k < n; k++) {
        if (c.containPixel({ gridIndex: k }, [ev.offsetX, ev.offsetY])) {
          const v = c.convertFromPixel({ gridIndex: k }, [ev.offsetX, ev.offsetY])[0];
          cb.current.onSelect(nearestIndex(xs, v));
          return;
        }
      }
    });
    // 範囲 → 地図
    c.on("datazoom", () => {
      const dz = (c.getOption() as { dataZoom: { startValue: number; endValue: number; start: number; end: number }[] }).dataZoom[0];
      if (dz.start <= 0.01 && dz.end >= 99.99) return cb.current.onRange(null);
      cb.current.onRange([nearestIndex(xs, dz.startValue), nearestIndex(xs, dz.endValue)]);
    });

    const ro = new ResizeObserver(() => c.resize());
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, panels, ranked, xs]);

  // 地図側のカーソル → グラフのカーソル
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    if (hover === null) c.dispatchAction({ type: "hideTip" });
    else c.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: hover });
  }, [hover]);

  // 選択した窓の縦線（全段）
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const muted = cssVar("--ink");
    c.setOption({
      series: panels.map((p) => ({
        id: p.key,
        markLine: {
          silent: true,
          symbol: "none",
          animation: false,
          lineStyle: { color: muted, type: "dashed" },
          label: { show: false },
          data: [
            ...(p.threshold !== undefined ? [{ yAxis: p.threshold, lineStyle: { color: cssVar("--muted") }, label: { show: true, formatter: `${p.threshold}`, color: cssVar("--muted") } }] : []),
            ...(selected !== null ? [{ xAxis: xs[selected], lineStyle: { color: muted, width: 1.5, type: "solid" } }] : []),
          ],
        },
      })),
    });
  }, [selected, panels, xs, data]);

  return <div ref={box} className="h-full w-full" />;
}
