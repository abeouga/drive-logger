// 地図（MapLibre GL ＋ OpenFreeMap）。軌跡を 1 秒窓の線分で描き、log_rms の 5 分位で塗る。
// - 自宅周辺の窓はデータに座標が入っていないので、線も点もない
// - 線にカーソルを置く → onHover、クリック → onSelect（タイムラインと詳細パネルが追従）
// - タイムラインのカーソル（hover）と選択（selected）を地図上の点で示す
// - タイムラインで範囲を選ぶと（range）、その区間に寄る
import { useEffect, useMemo, useRef, useState } from "react";
import { Map as MLMap, NavigationControl, ScaleControl, setWorkerUrl, type GeoJSONSource, type LngLatBoundsLike, type MapLayerMouseEvent, type ErrorEvent } from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import workerSrc from "maplibre-gl/dist/maplibre-gl-worker.mjs?raw";
import type { RideData } from "../lib/data";
import { MAP_STYLE, QUINTILE } from "../lib/colors";
import { hasCoord, type Selection } from "../lib/series";
import { cssVar, type Theme } from "../lib/theme";

// 1 ファイル配信ではワーカーの .mjs が別に置けないので、文字列から Blob URL を作って渡す
setWorkerUrl(URL.createObjectURL(new Blob([workerSrc], { type: "text/javascript" })));

interface Props {
  data: RideData;
  theme: Theme;
  hover: Selection;
  selected: Selection;
  range: [number, number] | null;
  ranked: number[];
  onHover: (i: Selection) => void;
  onSelect: (i: Selection) => void;
}

type FC = FeatureCollection;

function segments(d: RideData): FC {
  const c = d.columns;
  const features: Feature[] = [];
  for (let i = 0; i < d.n - 1; i++) {
    if (!hasCoord(d, i) || !hasCoord(d, i + 1)) continue; // 欠損・マスクの区間は線をつながない
    features.push({
      type: "Feature",
      properties: { i, cls: Math.max(c.cls[i], c.cls[i + 1], 0) },
      geometry: { type: "LineString", coordinates: [[c.lon[i]!, c.lat[i]!], [c.lon[i + 1]!, c.lat[i + 1]!]] },
    });
  }
  return { type: "FeatureCollection", features };
}

function points(d: RideData, idx: number[], props: (i: number, k: number) => Record<string, unknown> = () => ({})): FC {
  return {
    type: "FeatureCollection",
    features: idx
      .filter((i) => i !== null && hasCoord(d, i))
      .map((i, k) => ({
        type: "Feature",
        properties: { i, ...props(i, k) },
        geometry: { type: "Point", coordinates: [d.columns.lon[i]!, d.columns.lat[i]!] },
      })),
  };
}

function bounds(d: RideData, from = 0, to = d.n - 1): LngLatBoundsLike | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (let i = from; i <= to; i++) {
    if (!hasCoord(d, i)) continue;
    const lon = d.columns.lon[i]!, lat = d.columns.lat[i]!;
    w = Math.min(w, lon); e = Math.max(e, lon); s = Math.min(s, lat); n = Math.max(n, lat);
  }
  return Number.isFinite(w) ? [[w, s], [e, n]] : null;
}

export default function MapView({ data, theme, hover, selected, range, ranked, onHover, onSelect }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const ready = useRef(false);
  const applyPoints = useRef<() => void>(() => {});
  const [failed, setFailed] = useState<string | null>(null);
  const cb = useRef({ onHover, onSelect });
  cb.current = { onHover, onSelect };

  const segs = useMemo(() => segments(data), [data]);
  // 見どころ：順位の番号付きの丸（色は文字色。状態の色や系列の色は使わない）
  const marks = useMemo(() => points(data, ranked, (_i, k) => ({ rank: k + 1 })), [data, ranked]);

  // 地図を作る（走行・明暗が変わったら作り直す）
  useEffect(() => {
    if (!box.current) return;
    const b = bounds(data);
    const m = new MLMap({
      container: box.current,
      style: MAP_STYLE[theme],
      bounds: b ?? undefined,
      fitBoundsOptions: { padding: 32 },
      attributionControl: { compact: true },
      // ページの一部に置いた地図なので、ホイールはページのスクロールに使い、拡大縮小は Ctrl（⌘）＋ホイールにする
      cooperativeGestures: true,
      locale: {
        "CooperativeGesturesHandler.WindowsHelpText": "Ctrl キーを押しながらスクロールすると地図を拡大・縮小できます",
        "CooperativeGesturesHandler.MacHelpText": "⌘ キーを押しながらスクロールすると地図を拡大・縮小できます",
        "CooperativeGesturesHandler.MobileHelpText": "2 本の指で地図を動かせます",
        "NavigationControl.ZoomIn": "拡大",
        "NavigationControl.ZoomOut": "縮小",
      },
    });
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    // 枠の大きさがレイアウトで変わったら描き直す（作った直後に幅が決まることがある）
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(box.current);
    map.current = m;
    ready.current = false;
    setFailed(null);
    m.on("error", (e: ErrorEvent) => {
      console.error("map error", e.error);
      if (!ready.current) setFailed(e.error?.message ?? "不明なエラー");
    });

    m.on("load", () => {
      const ink = cssVar("--ink");
      const surface = cssVar("--surface");
      const accent = cssVar("--accent");
      const ramp = QUINTILE[theme];
      m.addSource("segs", { type: "geojson", data: segs });
      m.addSource("marks", { type: "geojson", data: marks });
      m.addSource("cursor", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addSource("selected", { type: "geojson", data: { type: "FeatureCollection", features: [] } });

      // 線の下に地図面の色の縁取りを敷き、交差や背景との境目をはっきりさせる
      m.addLayer({ id: "segs-casing", type: "line", source: "segs", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": surface, "line-width": 7 } });
      m.addLayer({
        id: "segs",
        type: "line",
        source: "segs",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["match", ["get", "cls"], 0, ramp[0], 1, ramp[1], 2, ramp[2], 3, ramp[3], ramp[4]], "line-width": 4 },
      });
      // クリックしやすいように、透明の太い線を当たり判定に使う
      m.addLayer({ id: "segs-hit", type: "line", source: "segs", paint: { "line-color": "#000", "line-opacity": 0, "line-width": 16 } });

      m.addLayer({ id: "marks", type: "circle", source: "marks", paint: { "circle-radius": 9, "circle-color": ink, "circle-stroke-color": surface, "circle-stroke-width": 2 } });
      m.addLayer({
        id: "marks-label",
        type: "symbol",
        source: "marks",
        layout: { "text-field": ["to-string", ["get", "rank"]], "text-size": 11, "text-font": ["Noto Sans Bold"], "text-allow-overlap": true },
        paint: { "text-color": surface },
      });
      // 選んだ窓の輪は見どころの丸より上に描く
      m.addLayer({ id: "selected", type: "circle", source: "selected", paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": accent, "circle-stroke-width": 3 } });
      m.addLayer({ id: "cursor", type: "circle", source: "cursor", paint: { "circle-radius": 7, "circle-color": accent, "circle-stroke-color": surface, "circle-stroke-width": 2 } });

      for (const layer of ["segs-hit", "marks"]) {
        m.on("mousemove", layer, (e: MapLayerMouseEvent) => {
          m.getCanvas().style.cursor = "pointer";
          const i = e.features?.[0]?.properties?.i;
          if (typeof i === "number") cb.current.onHover(i);
        });
        m.on("mouseleave", layer, () => {
          m.getCanvas().style.cursor = "";
          cb.current.onHover(null);
        });
        m.on("click", layer, (e: MapLayerMouseEvent) => {
          const i = e.features?.[0]?.properties?.i;
          if (typeof i === "number") cb.current.onSelect(i);
        });
      }
      ready.current = true;
      // 枠の大きさが確定した後で、もう一度全体を表示する
      m.resize();
      if (b) m.fitBounds(b, { padding: 32, duration: 0 });
      // 読み込み中に届いたカーソル・選択をここで反映する
      applyPoints.current();
    });
    return () => {
      ro.disconnect();
      ready.current = false;
      m.remove();
      map.current = null;
    };
  }, [data, theme, segs, marks]);

  // カーソル位置と選択の点（地図の準備前なら、準備完了時に load の中で反映する）
  applyPoints.current = () => {
    const m = map.current;
    if (!m || !ready.current) return;
    (m.getSource("cursor") as GeoJSONSource | undefined)?.setData(points(data, hover !== null ? [hover] : []));
    (m.getSource("selected") as GeoJSONSource | undefined)?.setData(points(data, selected !== null ? [selected] : []));
  };
  useEffect(() => applyPoints.current(), [data, hover, selected]);

  // 選んだ窓が画面の外なら寄せる
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current || selected === null || !hasCoord(data, selected)) return;
    const ll: [number, number] = [data.columns.lon[selected]!, data.columns.lat[selected]!];
    if (!m.getBounds().contains(ll)) m.easeTo({ center: ll, duration: 500 });
  }, [data, selected]);

  // タイムラインの範囲に寄る（全体に戻したら全体を表示）
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    const b = range ? bounds(data, range[0], range[1]) : bounds(data);
    if (b) m.fitBounds(b, { padding: 32, duration: 500, maxZoom: 17 });
  }, [data, range]);

  return (
    <div className="relative h-full w-full">
      <div ref={box} className="h-full w-full" />
      {failed && (
        <div className="absolute inset-x-3 top-3 rounded border border-line bg-surface p-3 text-xs text-ink-2">
          地図を読み込めませんでした（{failed}）。タイムラインと詳細パネルはそのまま使えます。
        </div>
      )}
    </div>
  );
}
