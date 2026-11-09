import { useState } from "react";
import { useRides } from "../lib/data";
import { fmtDuration, fmtKm } from "../lib/format";
import RideCard from "../components/RideCard";
import LoadState from "../components/LoadState";
import PageHeader from "../components/PageHeader";
import SortSelect from "../components/SortSelect";
import {
  DEFAULT_RIDE_SORT,
  RIDE_SORT_OPTIONS,
  isRideSortKey,
  listHashWithSort,
  sortFromHash,
  sortRides,
  type RideSortKey,
} from "../lib/rideSort";

// 選んだ並べ方は URL のハッシュ（#/?sort=…）に持つ。メニューや「← 走行一覧」から ?sort= なしで戻ったときのために、
// 同じタブの中では sessionStorage にも残す（使えない環境では残さない）
const SORT_STORAGE_KEY = "rideList.sort";

function initialSort(): RideSortKey {
  const fromHash = sortFromHash(window.location.hash);
  if (fromHash) return fromHash;
  try {
    const stored = sessionStorage.getItem(SORT_STORAGE_KEY);
    if (isRideSortKey(stored)) return stored;
  } catch {
    // 保存先が使えなくても既定の並べ方で出す
  }
  return DEFAULT_RIDE_SORT;
}

function saveSort(key: RideSortKey) {
  // ハッシュの書き換えで hashchange を起こさない（画面の先頭へ戻らないように）
  window.history.replaceState(null, "", listHashWithSort(key));
  try {
    sessionStorage.setItem(SORT_STORAGE_KEY, key);
  } catch {
    // 保存できなくても、今の画面とハッシュには効いている
  }
}

function Tile({ label, value, unit, note }: { label: string; value: string; unit?: string; note?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="mt-1 text-2xl font-semibold">
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-ink-2">{unit}</span>}
      </div>
      {note && <div className="mt-1 text-xs leading-snug text-muted">{note}</div>}
    </div>
  );
}

export default function RideList() {
  const { rides, ledger, error } = useRides();
  const [sort, setSort] = useState<RideSortKey>(initialSort);
  const originalName = new Map((ledger ?? []).map((r) => [r.id, r.original_name]));
  if (!rides) return <LoadState error={error} label="走行一覧" />;
  const sorted = sortRides(rides, sort);
  const totalS = rides.reduce((s, r) => s + r.duration_s, 0);
  const totalKm = rides.reduce((s, r) => s + (r.gps === "none" ? 0 : r.distance_km), 0);
  const nGps = rides.filter((r) => r.gps !== "none").length;
  const nZ = rides.reduce((s, r) => s + r.n_anomaly_z, 0);
  const nHl = rides.reduce((s, r) => s + r.n_highlights, 0);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="走行一覧" />

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="走行" value={String(rides.length)} unit="本" note={`GPS あり ${nGps} 本`} />
        <Tile label="記録時間（合計）" value={fmtDuration(totalS)} />
        <Tile label="距離（GPS ありの合計）" value={fmtKm(totalKm)} unit="km" />
        <Tile
          label="見どころ"
          value={String(nHl)}
          unit="か所"
          note={nZ === 0 ? "大きな揺れはなし。各走行で目立つ所を表示" : `うち大きな揺れ ${nZ} か所`}
        />
      </section>

      <section>
        <div className="mb-3 flex justify-end">
          <SortSelect
            value={sort}
            options={RIDE_SORT_OPTIONS}
            onChange={(key) => {
              setSort(key);
              saveSort(key);
            }}
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((r) => (
            <RideCard key={r.id} ride={r} originalName={originalName.get(r.id) ?? null} />
          ))}
        </div>
      </section>
    </div>
  );
}
