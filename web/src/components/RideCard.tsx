import { deleteRide, type RideSummary } from "../lib/data";
import { useAuth } from "../lib/auth/AuthGate";
import ActionButton from "./ActionButton";
import { fmtDate, fmtDuration, fmtKm, fmtTime } from "../lib/format";
import { rideHref } from "../lib/route";
import Sparkline from "./Sparkline";

const GPS_LABEL = { full: "GPS あり", partial: "GPS 一部", none: "GPS なし" } as const;
const SHORT_S = 5 * 60;

export function Badge({ children, tone = "plain" }: { children: React.ReactNode; tone?: "plain" | "accent" | "muted" }) {
  const cls =
    tone === "accent"
      ? "bg-accent-wash text-ink"
      : tone === "muted"
        ? "border border-dashed border-line text-ink-2"
        : "border border-line text-ink-2";
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] leading-none ${cls}`}>{children}</span>;
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="tabular text-sm text-ink">
        {value}
        {unit && <span className="ml-0.5 text-[11px] text-ink-2">{unit}</span>}
      </div>
    </div>
  );
}

export default function RideCard({ ride, originalName = null }: { ride: RideSummary; originalName?: string | null }) {
  const { isAdmin } = useAuth();
  const short = ride.duration_s < SHORT_S;
  const when = ride.start_ms !== null ? `${fmtDate(ride.start_ms)} ${fmtTime(ride.start_ms)}` : "日時不明（GPS なし）";
  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface transition hover:border-accent">
    <a
      href={rideHref(ride.id)}
      className="group flex flex-1 flex-col gap-3 rounded-lg p-4 focus-visible:outline-2 focus-visible:outline-accent"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm text-ink-2">{when}</div>
          <div className="font-semibold">{ride.id}</div>
          {originalName && <div className="text-[11px] text-muted">元の名前 {originalName}</div>}
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
        <div className="mb-1 flex items-baseline justify-between text-[11px] text-muted">
          <span>振動 rms（1 秒ごと）</span>
          <span className="tabular">中央値 {ride.rms_median.toFixed(2)} g</span>
        </div>
        <Sparkline values={ride.spark} durationS={ride.duration_s} />
      </div>

      {ride.memo && <p className="line-clamp-2 text-xs text-ink-2">{ride.memo}</p>}

      <div className="mt-auto flex items-center justify-between text-xs text-ink-2">
        <span>
          見どころ <span className="tabular text-ink">{ride.n_highlights}</span> 窓
        </span>
        <span className="text-accent opacity-0 transition group-hover:opacity-100">開く →</span>
      </div>
    </a>
    {isAdmin && (
      <div className="flex justify-end border-t border-line px-4 py-2">
        <ActionButton
          label="この走行を消す"
          tone="danger"
          confirmText={`${ride.id} を画面と学習から外します。生データは残り、ゴミ箱から戻せます。よろしいですか？`}
          onRun={() => deleteRide(ride.id)}
        />
      </div>
    )}
    </div>
  );
}
