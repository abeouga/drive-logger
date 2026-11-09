// スペクトログラム：横＝時刻（1 秒窓）、縦＝周波数 0〜200 Hz、濃さ＝その周波数の振動の強さ（走行の中での相対値）。
// 画像は Python が書き出した「強さ＝不透明度」の PNG。主の色（--accent）をその形で塗る（CSS の mask）。
// 下段は速度（GPS なしの走行は rms）。カーソル・クリック・範囲はタイムラインと同じく地図・詳細と共有する。
import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, AxisPointerComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { RideData, SpecMeta } from "../lib/data";
import { fmtElapsed, fmtTimeSec } from "../lib/format";
import { nearestIndex, xValues, type Selection } from "../lib/series";
import { cssVar } from "../lib/theme";

echarts.use([LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, AxisPointerComponent, CanvasRenderer]);

interface Props {
  data: RideData;
  spec: { meta: SpecMeta; url: string };
  hover: Selection;
  selected: Selection;
  onHover: (i: Selection) => void;
  onSelect: (i: Selection) => void;
  onRange: (r: [number, number] | null) => void;
}

// 段の位置（px）。画像の重ね合わせのために固定する
const L = 56, R = 16, TOP = 28, H0 = 230, GAP = 34, H1 = 90, BOTTOM = 58;
export const SPEC_HEIGHT = TOP + H0 + GAP + H1 + BOTTOM;

export default function Spectrogram({ data, spec, hover, selected, onHover, onSelect, onRange }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const cb = useRef({ onHover, onSelect, onRange });
  cb.current = { onHover, onSelect, onRange };
  const xs = useMemo(() => xValues(data), [data]);
  const abs = data.has_abs_time;
  const gps = data.columns.has_gps.some(Boolean);
  const half = (abs ? 1000 : 1) * spec.meta.window_sec / 2;
  const full: [number, number] = [xs[0] - half, xs[xs.length - 1] + half];
  // 画像の横の位置：今の表示範囲 [x0, x1] に合わせて mask の大きさと位置を変える
  const [view, setView] = useState<{ x0: number; x1: number; w: number }>({ x0: full[0], x1: full[1], w: 0 });
  const fmtX = (v: number) => (abs ? fmtTimeSec(v) : fmtElapsed(v));

  const lower = useMemo(() => {
    const c = data.columns;
    return gps
      ? { name: "速度（km/h）", values: c.speed, log: false, digits: 1, unit: "km/h" }
      : { name: "振動 rms（g）", values: c.rms.map((v) => (v !== null && v > 0 ? v : null)), log: true, digits: 3, unit: "g" };
  }, [data, gps]);

  useEffect(() => {
    if (!box.current) return;
    const ink = cssVar("--ink"), ink2 = cssVar("--ink-2"), muted = cssVar("--muted"), grid = cssVar("--grid"), axis = cssVar("--axis");
    const accent = cssVar("--accent"), surface = cssVar("--surface");
    const c = echarts.init(box.current);
    chart.current = c;
    const peak = spec.meta.peak_hz;
    const xAxis = (k: number) => ({
      gridIndex: k,
      type: abs ? "time" : "value",
      min: full[0],
      max: full[1],
      axisLine: { lineStyle: { color: axis } },
      axisTick: { show: false },
      axisLabel: { show: k === 1, color: muted, formatter: (v: number) => fmtX(v), hideOverlap: true },
      splitLine: { show: false },
    });
    c.setOption({
      animation: false,
      textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: ink2 },
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: ink }, label: { backgroundColor: ink, color: surface } },
      tooltip: {
        trigger: "axis",
        backgroundColor: surface,
        borderColor: grid,
        textStyle: { color: ink, fontSize: 12 },
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0]?.dataIndex;
          if (i === undefined) return "";
          const v = lower.values[i];
          const p = peak[i];
          return `<div style="font-variant-numeric:tabular-nums">${fmtX(xs[i])}</div>` +
            `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${ink2}">最も強い周波数（5 Hz 以上）</span><b>${p === null ? "—" : `${p} Hz`}</b></div>` +
            `<div style="display:flex;justify-content:space-between;gap:16px"><span style="color:${ink2}">${lower.name.replace(/（.*）/, "")}</span><b>${v === null ? "—" : `${v.toFixed(lower.digits)} ${lower.unit}`}</b></div>`;
        },
      },
      grid: [
        { left: L, right: R, top: TOP, height: H0 },
        { left: L, right: R, top: TOP + H0 + GAP, height: H1 },
      ],
      xAxis: [xAxis(0), xAxis(1)],
      yAxis: [
        {
          gridIndex: 0, type: "value", min: 0, max: spec.meta.f_max_hz, interval: 50,
          name: "周波数（Hz）", nameLocation: "end", nameGap: 8, nameTextStyle: { color: ink2, align: "left", fontSize: 12 },
          axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: muted, fontSize: 11 },
          splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
        },
        {
          gridIndex: 1, type: lower.log ? "log" : "value", name: lower.name, nameLocation: "end", nameGap: 8,
          nameTextStyle: { color: ink2, align: "left", fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false },
          axisLabel: { color: muted, fontSize: 11 }, splitLine: { lineStyle: { color: grid } }, splitNumber: 2,
        },
      ],
      dataZoom: [
        { type: "inside", xAxisIndex: [0, 1], filterMode: "none" },
        { type: "slider", xAxisIndex: [0, 1], filterMode: "none", height: 18, bottom: 8, borderColor: grid, labelFormatter: (v: number) => fmtX(v), textStyle: { color: muted } },
      ],
      series: [
        // 上段はカーソルを出すための見えない系列（画像は HTML 側で重ねる）
        { id: "spec", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: xs.map((x) => [x, 0]), showSymbol: false, lineStyle: { opacity: 0 }, itemStyle: { opacity: 0 }, silent: true },
        { id: "lower", type: "line", xAxisIndex: 1, yAxisIndex: 1, data: lower.values.map((v, i) => [xs[i], v]), showSymbol: false, connectNulls: false, lineStyle: { width: 1.5, color: accent }, itemStyle: { color: accent } },
      ],
    });
    setView({ x0: full[0], x1: full[1], w: c.getWidth() - L - R });

    c.on("updateAxisPointer", (e: unknown) => {
      const info = (e as { axesInfo?: { value: number }[] }).axesInfo?.[0];
      cb.current.onHover(info ? nearestIndex(xs, info.value) : null);
    });
    c.getZr().on("mouseout", () => cb.current.onHover(null));
    c.getZr().on("click", (ev: { offsetX: number; offsetY: number }) => {
      for (const k of [0, 1]) {
        if (c.containPixel({ gridIndex: k }, [ev.offsetX, ev.offsetY])) {
          cb.current.onSelect(nearestIndex(xs, c.convertFromPixel({ gridIndex: k }, [ev.offsetX, ev.offsetY])[0]));
          return;
        }
      }
    });
    c.on("datazoom", () => {
      const dz = (c.getOption() as { dataZoom: { startValue: number; endValue: number; start: number; end: number }[] }).dataZoom[0];
      setView({ x0: dz.startValue, x1: dz.endValue, w: c.getWidth() - L - R });
      if (dz.start <= 0.01 && dz.end >= 99.99) return cb.current.onRange(null);
      cb.current.onRange([nearestIndex(xs, dz.startValue), nearestIndex(xs, dz.endValue)]);
    });
    const ro = new ResizeObserver(() => {
      c.resize();
      setView((v) => ({ ...v, w: c.getWidth() - L - R }));
    });
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, spec, lower, xs]);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    if (hover === null) c.dispatchAction({ type: "hideTip" });
    else c.dispatchAction({ type: "showTip", seriesIndex: 1, dataIndex: hover });
  }, [hover]);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const ink = cssVar("--ink");
    const line = selected !== null ? [{ xAxis: xs[selected] }] : [];
    c.setOption({
      series: [
        { id: "spec", markLine: { silent: true, symbol: "none", animation: false, label: { show: false }, lineStyle: { color: ink, width: 1.5, type: "solid" }, data: line } },
        { id: "lower", markLine: { silent: true, symbol: "none", animation: false, label: { show: false }, lineStyle: { color: ink, width: 1.5, type: "solid" }, data: line } },
      ],
    });
  }, [selected, xs, spec]);

  // 画像の位置：表示範囲 [x0, x1] が上段の幅 w に広がるように、全体 [full0, full1] の画像を拡大・移動する
  const span = view.x1 - view.x0 || 1;
  const sizePx = (view.w * (full[1] - full[0])) / span;
  const posPx = (-view.w * (view.x0 - full[0])) / span;
  const mask = `url("${spec.url}")`;

  return (
    <div className="relative w-full" style={{ height: SPEC_HEIGHT }}>
      <div ref={box} className="absolute inset-0" />
      {view.w > 0 && (
        <div
          aria-hidden
          className="pointer-events-none absolute overflow-hidden"
          style={{ left: L, top: TOP, width: view.w, height: H0 }}
        >
          <div
            className="h-full w-full bg-accent"
            style={{
              maskImage: mask,
              WebkitMaskImage: mask,
              maskSize: `${sizePx}px 100%`,
              WebkitMaskSize: `${sizePx}px 100%`,
              maskPosition: `${posPx}px 0`,
              WebkitMaskPosition: `${posPx}px 0`,
              maskRepeat: "no-repeat",
              WebkitMaskRepeat: "no-repeat",
            }}
          />
        </div>
      )}
    </div>
  );
}
