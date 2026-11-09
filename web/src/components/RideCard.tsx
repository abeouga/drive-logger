import type { RideSummary } from "../lib/data";
import { useAuth } from "../lib/auth/AuthGate";
import { fmtDate, fmtDuration, fmtKm, fmtTime } from "../lib/format";
import { rideHref } from "../lib/route";
import Sparkline from "./Sparkline";
import TrashButton from "./TrashButton";

const GPS_LABEL = { full: "GPS あり", partial: "GPS 一部", none: "GPS なし" } as const;
const SHORT_S = 5 * 60;

export function Badge({ children, tone = "plain" }: { children: React.ReactNode; tone?: "plain" | "accent" | "muted" }) {
  const cls = tone === "accent" ? "pill-accent" : "pill-muted";
  return <span className={`pill ${cls}`}>{children}</span>;
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="tabular text-sm text-ink">
        {value}
        {unit && <span className="ml-0.5 text-xs text-ink-2">{unit}</span>}
      </div>
    </div>
  );
}

export default function RideCard({ ride, originalName = null }: { ride: RideSummary; originalName?: string | null }) {
  const { isAdmin } = useAuth();
  const short = ride.duration_s < SHORT_S;
  const when = ride.start_ms !== null ? `${fmtDate(ride.start_ms)} ${fmtTime(ride.start_ms)}` : "日時不明（GPS なし）";
  return (
    // ゴミ箱のボタンはリンクの外に重ねて置く（リンクの中にボタンを入れない。押しても走行の画面へ移らない）
    <div className="card relative flex flex-col transition hover:border-accent">
    <a
      href={rideHref(ride.id)}
      className="group flex flex-1 flex-col gap-3 rounded-[12px] p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm text-ink-2">{when}</div>
          <div className="font-semibold">{ride.id}</div>
          {originalName && <div className="text-xs text-muted">元の名前 {originalName}</div>}
        </div>
        <div className="flex flex-wrap justify-end gap-1">
          <Badge tone={ride.gps === "none" ? "muted" : "accent"}>{GPS_LABEL[ride.gps]}</Badge>
          {short && <Badge>短い記録</Badge>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat label="時間" value={fmtDuration(ride.duration_s)} />
        <Stat label="距離" value={ride.gps === "none" ? "—" : fmtKm(ride.distance_km)} unit={ride.gps === "none" ? undefined : "km"} />
        <Stat label="最高速度" value={ride.max_speed_kmh === null ? "—" : ride.max_speed_kmh.toFixed(0)} unit={ride.max_speed_kmh === null ? undefined : "km/h"} />
      </div>

      <div>
        <div className="mb-1 flex items-baseline justify-between text-xs text-muted">
          <span>振動 rms（1 秒ごと）</span>
          <span className="tabular">中央値 {ride.rms_median.toFixed(2)} g</span>
        </div>
        <Sparkline values={ride.spark} durationS={ride.duration_s} />
      </div>

      {ride.memo && <p className="line-clamp-2 text-xs text-ink-2">{ride.memo}</p>}

      <div className={`mt-auto flex min-h-[34px] items-center justify-between text-xs text-ink-2 ${isAdmin ? "pr-11" : ""}`}>
        <span>
          見どころ <span className="tabular text-ink">{ride.n_highlights}</span> 窓
        </span>
        <span className="font-bold text-accent opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">開く →</span>
      </div>
    </a>
    {isAdmin && (
      <div className="absolute right-4 bottom-4">
        <TrashButton rideId={ride.id} />
      </div>
    )}
    </div>
  );
}
