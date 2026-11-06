// 表示用の整形（日本時間・時間・距離）

const jstDate = new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", weekday: "short" });
const jstTime = new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit" });
const jstTimeSec = new Intl.DateTimeFormat("ja-JP", { timeZone: "Asia/Tokyo", hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const fmtDate = (ms: number) => jstDate.format(ms);
export const fmtTime = (ms: number) => jstTime.format(ms);
export const fmtTimeSec = (ms: number) => jstTimeSec.format(ms);

/** 秒 → 「13 分」「1 時間 5 分」 */
export function fmtDuration(s: number): string {
  const m = Math.round(s / 60);
  if (m < 60) return `${m} 分`;
  return `${Math.floor(m / 60)} 時間 ${m % 60} 分`;
}

/** 秒 → 「12:34」（起動からの経過） */
export function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export const fmtKm = (km: number) => (km >= 10 ? km.toFixed(0) : km.toFixed(1));
