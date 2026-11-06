import { rides } from "../lib/data";
import { fmtDuration, fmtKm } from "../lib/format";
import RideCard from "../components/RideCard";

function Tile({ label, value, unit, note }: { label: string; value: string; unit?: string; note?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-ink-2">{unit}</span>}
      </div>
      {note && <div className="mt-1 text-[11px] leading-snug text-muted">{note}</div>}
    </div>
  );
}

export default function RideList() {
  // 記録の番号（ride_NNN）は電源を入れた順。新しい順に並べる（GPS なしの走行は日時が分からないため番号で並べる）
  const sorted = [...rides].sort((a, b) => b.id.localeCompare(a.id));
  const totalS = rides.reduce((s, r) => s + r.duration_s, 0);
  const totalKm = rides.reduce((s, r) => s + (r.gps === "none" ? 0 : r.distance_km), 0);
  const nGps = rides.filter((r) => r.gps !== "none").length;
  const nZ = rides.reduce((s, r) => s + r.n_anomaly_z, 0);
  const nHl = rides.reduce((s, r) => s + r.n_highlights, 0);

  return (
    <div className="flex flex-col gap-6">
      <section>
        <h1 className="text-xl font-semibold">走行一覧</h1>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-2">
          ハンターカブ CT125 に載せた ESP32 ロガー（GPS ＋ 加速度センサー）の記録です。1 秒ごとの振動を、地図とタイムラインで見られます。
          GPS が取れなかった走行は、地図なしのタイムラインだけを表示します。
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="走行" value={String(rides.length)} unit="本" note={`GPS あり ${nGps} 本`} />
        <Tile label="記録時間（合計）" value={fmtDuration(totalS)} />
        <Tile label="距離（GPS ありの合計）" value={fmtKm(totalKm)} unit="km" />
        <Tile
          label="見どころ"
          value={String(nHl)}
          unit="窓"
          note={nZ === 0 ? "z_speed > 3 の窓はなし。各走行のスコア上位を表示" : `うち z_speed > 3 が ${nZ} 窓`}
        />
      </section>

      <section>
        <div className="mb-2 text-xs text-muted">新しい順（記録番号順）</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((r) => (
            <RideCard key={r.id} ride={r} />
          ))}
        </div>
      </section>
    </div>
  );
}
