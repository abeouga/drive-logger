// 選んだ 1 秒の生波形（平均を引いた 3 軸と、そこから求めた合成）。
// 上段：合成（重力除去後の大きさ。rms の元になる量）、下段：3 軸（センサー基板の軸のまま）。
import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Waveform } from "../lib/data";
import { SERIES } from "../lib/colors";
import { cssVar } from "../lib/theme";

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export default function WaveChart({ wave }: { wave: Waveform }) {
  const box = useRef<HTMLDivElement>(null);
  const series = useMemo(() => {
    const ms = wave.ax.map((_, k) => +((k / wave.fs) * 1000).toFixed(1));
    const g = (v: number) => v / 1000;
    const mag = wave.ax.map((_, k) => Math.hypot(wave.ax[k], wave.ay[k], wave.az[k]) / 1000);
    return {
      mag: ms.map((t, k) => [t, mag[k]]),
      axes: [
        { name: "X 軸", data: ms.map((t, k) => [t, g(wave.ax[k])]) },
        { name: "Y 軸", data: ms.map((t, k) => [t, g(wave.ay[k])]) },
        { name: "Z 軸", data: ms.map((t, k) => [t, g(wave.az[k])]) },
      ],
    };
  }, [wave]);

  useEffect(() => {
    if (!box.current) return;
    const ink = cssVar("--ink"), ink2 = cssVar("--ink-2"), muted = cssVar("--muted"), grid = cssVar("--grid"), axis = cssVar("--axis"), surface = cssVar("--surface");
    const c = echarts.init(box.current);
    const xAxis = (k: number) => ({
      gridIndex: k,
      type: "value",
      min: 0,
      max: 1000,
      axisLine: { lineStyle: { color: axis } },
      axisTick: { show: false },
      axisLabel: { show: k === 1, color: muted, formatter: (v: number) => `${v} ms` },
      splitLine: { show: false },
    });
    const yAxis = (k: number, name: string) => ({
      gridIndex: k,
      type: "value",
      name,
      nameLocation: "end",
      nameGap: 6,
      nameTextStyle: { color: ink2, align: "left", fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 10 },
      splitLine: { lineStyle: { color: grid } },
      splitNumber: 2,
    });
    c.setOption({
      animation: false,
      textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: ink2 },
      legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 2, textStyle: { color: ink2, fontSize: 11 }, data: ["X 軸", "Y 軸", "Z 軸"] },
      tooltip: {
        trigger: "axis",
        backgroundColor: surface,
        borderColor: grid,
        textStyle: { color: ink, fontSize: 11 },
        valueFormatter: (v: number) => `${v.toFixed(3)} g`,
      },
      axisPointer: { link: [{ xAxisIndex: "all" }], lineStyle: { color: muted } },
      grid: [
        { left: 40, right: 36, top: 26, height: "30%" },
        { left: 40, right: 36, top: "55%", bottom: 22 },
      ],
      xAxis: [xAxis(0), xAxis(1)],
      yAxis: [yAxis(0, "合成（g）"), yAxis(1, "各軸（g）")],
      series: [
        { name: "合成", type: "line", xAxisIndex: 0, yAxisIndex: 0, data: series.mag, showSymbol: false, lineStyle: { width: 1.5, color: ink }, itemStyle: { color: ink } },
        ...series.axes.map((s, k) => ({
          name: s.name,
          type: "line",
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: s.data,
          showSymbol: false,
          lineStyle: { width: 1.2, color: SERIES[k] },
          itemStyle: { color: SERIES[k] },
          // 線の右端に軸の名前（色だけに頼らない）
          endLabel: { show: true, formatter: s.name.replace(" 軸", ""), color: ink2, fontSize: 10 },
        })),
      ],
    });
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      c.dispose();
    };
  }, [series]);

  return <div ref={box} className="h-[220px] w-full" />;
}
