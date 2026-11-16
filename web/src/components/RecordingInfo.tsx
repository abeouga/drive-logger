// 走行の画面の見出しに出す、加速度の記録の設定（版・センサーとつなぎ方・速さ・振り切れる大きさ）。
// 400 Hz と 800 Hz（のちに SPI の 1600〜3200 Hz）の走行が混ざるので、振動の見え方の違いが設定の違いかどうかを見分けるため。
import type { RecordingSettings } from "../lib/types";
import { firmwareLabel, isSlowerThanSet, rateBadge, recordingNote, sensorLabel } from "../lib/recording";

export default function RecordingInfo({ recording }: { recording?: RecordingSettings }) {
  if (!recording) {
    return (
      <span title="この走行は、記録の設定を画面に出す前に処理したので、設定が分かりません">
        <span className="text-ink-2">記録 </span>
        <span className="text-muted">不明</span>
      </span>
    );
  }
  const slow = isSlowerThanSet(recording);
  const parts = [
    firmwareLabel(recording.firmware),
    sensorLabel(recording),
    rateBadge(recording),
    recording.accel_range_g !== null ? `±${recording.accel_range_g} g` : null,
  ].filter((p): p is string => p !== null);
  return (
    <span title={recordingNote(recording)}>
      <span className="text-ink-2">記録 </span>
      {parts.join("・")}
      <span className={slow ? "ml-1 font-semibold text-accent" : "ml-1 text-ink-2"}>
        （実測 {recording.accel_fs_hz.toFixed(1)} Hz{slow ? "・設定より遅い" : ""}）
      </span>
    </span>
  );
}
