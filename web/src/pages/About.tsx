// この分析について：何を作ったか・処理の流れ・構成・基準を超えた振動の決め方・できたこと／できていないこと・表現の決まり
import { loadModel, loadModels, useLoad, useRides, type AnomalyMethod, type ModelRecord } from "../lib/data";
import { fmtDuration } from "../lib/format";
import ModelInfo from "../components/ModelInfo";
import PageHeader from "../components/PageHeader";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="flex flex-col gap-2 text-sm leading-relaxed text-ink-2">{children}</div>
    </section>
  );
}

function Box({ title, body, future = false }: { title: string; body: string; future?: boolean }) {
  return (
    <div className={`flex-1 px-3 py-2 ${future ? "rounded-[12px] border border-dashed border-line-strong bg-surface-muted" : "card"}`}>
      <div className={`text-sm font-semibold ${future ? "text-ink-2" : "text-ink"}`}>{title}</div>
      <div className="text-xs leading-snug text-ink-2">{body}</div>
    </div>
  );
}

function Arrow() {
  return (
    <div aria-hidden className="flex shrink-0 items-center justify-center text-muted md:px-1">
      <span className="md:hidden">↓</span>
      <span className="hidden md:inline">→</span>
    </div>
  );
}

/** 判定の方法ごとの説明。方法の名前は画面用データ（rides.json の anomaly_method）から選び、文に決め打ちしない */
type JudgedMethod = Exclude<AnomalyMethod, "none">;
const METHOD_TEXT: Record<JudgedMethod, { what: string; score: string; note?: string }> = {
  speed_baseline: { what: "速度で補正した正常時のベースラインからの逸脱", score: "z_speed" },
  speed_iforest: {
    what: "速度と振動の特徴量で学習した Isolation Forest（まれな組み合わせを見つける手法）のスコア",
    score: "score_if",
    note: "Isolation Forest は静かすぎる 1 秒にも高いスコアを付けるため、その速度でのふだんの振動（中央値）より大きい 1 秒だけを数えています。",
  },
};

/** 今使っているモデルの記録から、方法ごとのしきい値を読む（読めなければ null） */
function modelThreshold(record: ModelRecord | null, method: JudgedMethod): number | null {
  if (method === "speed_iforest") return record?.forest?.threshold ?? null;
  const model = record?.config.model as Record<string, unknown> | undefined;
  return typeof model?.z_threshold === "number" ? model.z_threshold : null;
}

/** しきい値の決め方の説明（speed_iforest は学習データの分位点） */
function thresholdText(record: ModelRecord | null, method: JudgedMethod): string {
  const threshold = modelThreshold(record, method);
  if (method === "speed_iforest") {
    const top = record?.forest ? `上位 ${+((1 - record.forest.quantile) * 100).toFixed(3)}%` : "上位の決まった割合";
    return threshold === null
      ? `しきい値（学習に使った 1 秒のスコアの${top}に当たる値。「今使っているモデル」の記録）`
      : `しきい値（${threshold.toFixed(4)}。学習に使った 1 秒のスコアの${top}に当たる値で、「今使っているモデル」の記録）`;
  }
  return threshold === null ? "しきい値（「今使っているモデル」の設定）" : `しきい値（${threshold}、「今使っているモデル」の設定）`;
}

function AnomalyRule({ methods }: { methods: JudgedMethod[] }) {
  const models = useLoad(loadModels, []);
  const current = models.value?.current ?? null;
  const record = useLoad(async () => (current ? loadModel(current) : null), [current]);
  if (methods.length === 0) return <p>画面用データに判定の方法が入っていません（判定している走行が無いか、判定の方法を持たない古いデータです）。</p>;
  return (
    <>
      {methods.map((m) => (
        <p key={m}>
          {METHOD_TEXT[m].what}（{METHOD_TEXT[m].score}）を 1 秒ごとに求め、{thresholdText(record.value, m)}を超えた 1 秒だけを「基準を超えた振動」として出しています。
          {METHOD_TEXT[m].note && ` ${METHOD_TEXT[m].note}`}
          停止中（5 km/h 未満）の 1 秒は判定に入れません。超えた所が無い走行は「なし」と出します。
        </p>
      ))}
    </>
  );
}

export default function About() {
  const { rides } = useRides();
  const total = rides?.reduce((s, r) => s + r.duration_s, 0) ?? 0;
  const nGps = rides?.filter((r) => r.gps !== "none").length ?? 0;
  // 画面用データに入っている判定の方法（知らない方法と、方法の入っていない古いデータは読み飛ばす）
  const methods = [...new Set(rides?.map((r) => r.anomaly_method) ?? [])].filter((m): m is JudgedMethod => typeof m === "string" && m in METHOD_TEXT);

  return (
    <div className="flex max-w-4xl flex-col gap-8">
      <PageHeader title="この分析について">
        <p>
          ハンターカブ CT125 に、ESP32（マイコン）・GPS・加速度センサー・microSD で作ったロガーを載せ、走行中の振動を位置と時刻に結びつけて可視化しました。
          {rides && ` 画面に出している走行は ${rides.length} 本（合計 ${fmtDuration(total)}、うち GPS あり ${nGps} 本）です。`}
        </p>
      </PageHeader>

      <Section title="構成">
        <div className="flex flex-col gap-2 md:flex-row md:items-stretch">
          <Box title="記録と送信（ESP32）" body="加速度 約 400 Hz・GPS 1 Hz を microSD に記録し、走行後に家の Wi-Fi で S3 の生データの場所へ送る" />
          <Arrow />
          <Box title="処理（AWS Lambda）" body="届いたら前処理・走行の分類・点数付け。処理ごとの記録と走行の台帳を残し、台帳が指す結果だけを公開する" />
          <Arrow />
          <Box title="表示（このページ）" body="地図・タイムライン・スペクトログラムが連動。ログインした人だけがデータ API から読む" />
        </div>
        <div className="flex flex-col gap-2 md:flex-row">
          <Box future title="将来：SageMaker で学習" body="今は Lambda の学習し直しで足りる量。走行が増えたら移す" />
          <Box future title="将来：ECU の情報" body="端子・電圧・通信方式を安全に確かめてから" />
        </div>
        <p className="text-xs text-muted">実線の枠は今回作ったもの、点線の枠は設計だけで、まだ作っていないものです。</p>
      </Section>

      <Section title="処理の流れ">
        <ol className="list-decimal space-y-1 pl-5">
          <li>ESP32 の時計（起動からのマイクロ秒）と GPS の時刻を対応づけ、すべての記録に日本時間を付ける（GPS なしの走行は記録開始からの時間のみ）。</li>
          <li>加速度を 1 秒ずつに区切り、重力（各軸の平均）を引いた振動の大きさ（rms）・振れ幅・周波数帯ごとの割合を計算する。</li>
          <li>GPS は衛星数・HDOP・位置の飛び・速度の食い違いで品質を確かめ、悪い点は使わない。</li>
          <li>速度を 5 km/h ごとに区切り、それぞれの速度での「ふだんの振動の大きさ」（中央値とばらつき）を求める。各 1 秒がそこからどれだけ離れているかを z_speed とする。</li>
          <li>振動の特徴量と速度を合わせて Isolation Forest（まれな組み合わせを見つける手法）で学習し、GPS のある 1 秒にスコア（score_if）を付ける。しきい値は、学習に使った 1 秒のスコアの上位の決まった割合に当たる値にする。</li>
        </ol>
      </Section>

      <Section title="走行の分類と、学習に使う走行">
        <p>
          処理のたびに、振動と GPS から走行を自動で分類しています。机上（振動の中央値が 0.05 g 未満でエンジンの振動が無い）の走行は画面に出さず、
          停車（始点から 200 m 以上動いていない）と実走（200 m 以上動き、5 km/h 以上の 1 秒が 60 以上）だけを学習に使います。
          GPS が取れなかった走行（動いたか分からない）は画面には出しますが、学習には使いません。画面から消した走行も学習に使いません。
        </p>
      </Section>

      <Section title="今使っているモデル">
        <ModelInfo />
      </Section>

      <Section title="基準を超えた振動の決め方">
        {rides ? <AnomalyRule methods={methods} /> : <p>走行の一覧を読み込み中…</p>}
        <p>GPS がない走行は、速度が分からず速度で補正できないため、判定していません。</p>
        <p>
          画面に出している値は、健康な車両の走行データから作った「速度で補正した正常時のベースライン」からの逸脱、またはそのデータで学習したモデルから見た「まれさ」です。故障したときのデータは含まれていません。
          正解の分かっているデータが無いので、精度は出していません。確かめは、1 走行ずつ抜いて学習し、抜いた走行のスコアの上位を目で見る形で行いました。
        </p>
        <p>
          値が大きいのは「路面または車両に起因する振動の変化」があった場所です。段差・マンホール・荒れた舗装などの路面の影響が大きく、車両の異常と断定するものではありません。
        </p>
      </Section>

      <Section title="できたこと・確かめたこと">
        <ul className="list-disc space-y-1 pl-5">
          <li>最初の 9 本の記録すべてで、サンプルの欠け・時刻の重複・書き込みエラーがないことを確認した。</li>
          <li>速度が上がるほど振動が大きくなる傾向がはっきり出た（往路・復路とも）。</li>
          <li>停車中のアイドリングで 20〜26 Hz 付近に鋭い山が出る（スペクトログラムの横の帯）。</li>
          <li>GPS が取れなかった走行でも、時間軸のタイムラインとスペクトログラムで振動を見られるようにした。</li>
        </ul>
      </Section>

      <Section title="うまくいかなかったこと・できていないこと">
        <ul className="list-disc space-y-1 pl-5">
          <li>往路と復路で同じ場所の振動が一致するかを 20〜100 m の区画で比べたが、関係は確認できなかった（同じ区画を通った数が少なく、通過速度も往復で違うため）。</li>
          <li>郊外の 4 本は最初から最後まで GPS の衛星数が 0 だった。アンテナの接続が外れた可能性が高く、確認中。</li>
          <li>ロガーはブレッドボードのまま車体に置いただけの暫定の固定で、20 Hz 以上には置き方による揺れ（共振）も混ざっている可能性がある。</li>
          <li>
            ECU（エンジン制御）との通信は今回は対象外にした。端子・電圧・通信方式が未検証で、期限内に安全に確かめられないと判断し、
            動いている GPS と振動の 2 系統で、記録から表示まで一本につなげることを優先した。
          </li>
          <li>健康な車両の走行データだけで作っており、故障したときのデータは含まれていない。</li>
        </ul>
      </Section>

      <Section title="データの扱い">
        <ul className="list-disc space-y-1 pl-5">
          <li>データは非公開の S3 バケットに置き、ログインした人だけが、データ API を通して見られるようにしている。</li>
          <li>地図の背景（OpenFreeMap）を読み込むとき、表示している範囲がタイルのサーバーに伝わる。</li>
        </ul>
      </Section>
    </div>
  );
}
