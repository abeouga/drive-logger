// この分析について：何を作ったか・処理の流れ・構成・見どころの決め方・できたこと／できていないこと・表現の決まり
import { useRides } from "../lib/data";
import { fmtDuration } from "../lib/format";

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
    <div className={`flex-1 rounded-lg border bg-surface px-3 py-2 ${future ? "border-dashed border-line" : "border-ink/30"}`}>
      <div className={`text-sm font-semibold ${future ? "text-ink-2" : "text-ink"}`}>{title}</div>
      <div className="text-[11px] leading-snug text-ink-2">{body}</div>
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

export default function About() {
  const { rides } = useRides();
  const total = rides?.reduce((s, r) => s + r.duration_s, 0) ?? 0;
  const nGps = rides?.filter((r) => r.gps !== "none").length ?? 0;

  return (
    <div className="flex max-w-4xl flex-col gap-8">
      <div>
        <h1 className="text-xl font-semibold">この分析について</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          ハンターカブ CT125 に、ESP32（マイコン）・GPS・加速度センサー・microSD で作ったロガーを載せ、走行中の振動を位置と時刻に結びつけて可視化しました。
          {rides && ` 2026 年 11 月 2 日に ${rides.length} 本（合計 ${fmtDuration(total)}、うち GPS あり ${nGps} 本）を記録しています。`}
        </p>
      </div>

      <Section title="構成">
        <div className="flex flex-col gap-2 md:flex-row md:items-stretch">
          <Box title="記録（ESP32）" body="加速度 約 400 Hz・GPS 1 Hz を microSD に CSV で保存" />
          <Arrow />
          <Box title="解析（Python）" body="時刻をそろえ、1 秒ごとの振動の量と速度補正ベースラインからの逸脱を計算" />
          <Arrow />
          <Box title="保管（Amazon S3）" body="非公開のバケット。処理済みのデータとこのページを置く" />
          <Arrow />
          <Box title="表示（このページ）" body="地図・タイムライン・スペクトログラムが連動。署名付き URL で配る" />
        </div>
        <div className="flex flex-col gap-2 md:flex-row">
          <Box future title="将来：自動送信" body="走行後にスマホのテザリング経由で S3 へ（今は SD を PC にコピー）" />
          <Box future title="将来：クラウドで処理" body="S3 に届いたら Lambda で前処理、データが増えたら SageMaker で再学習" />
        </div>
        <p className="text-[11px] text-muted">実線の枠は今回作ったもの、点線の枠は設計だけで、まだ作っていないものです。</p>
      </Section>

      <Section title="処理の流れ">
        <ol className="list-decimal space-y-1 pl-5">
          <li>ESP32 の時計（起動からのマイクロ秒）と GPS の時刻を対応づけ、すべての記録に日本時間を付ける（GPS なしの走行は記録開始からの時間のみ）。</li>
          <li>加速度を 1 秒ずつに区切り、重力（各軸の平均）を引いた振動の大きさ（rms）・振れ幅・周波数帯ごとの割合を計算する。</li>
          <li>GPS は衛星数・HDOP・位置の飛び・速度の食い違いで品質を確かめ、悪い点は使わない。自宅の周辺 300 m は地図に出さないよう、座標そのものを消してから書き出す。</li>
          <li>速度を 5 km/h ごとに区切り、それぞれの速度での「ふだんの振動の大きさ」（中央値とばらつき）を求める。各 1 秒がそこからどれだけ離れているかを z_speed とする。</li>
          <li>速度を使わない見方として、振動の特徴量だけで Isolation Forest（まれな組み合わせを見つける手法）のスコアも付ける。</li>
        </ol>
      </Section>

      <Section title="見どころの決め方">
        <p>
          z_speed が 3 を超える 1 秒（速度で補正したベースラインから大きく離れた振動）を見どころとしています。今回の走行には 3 を超える 1 秒がなかったため、
          走行中の z_speed の上位 10 か所を示しています。GPS がない走行は速度で補正できないので、Isolation Forest のスコアの上位 10 か所です。
        </p>
        <p>
          値が大きいのは「路面または車両に起因する振動の変化」があった場所です。段差・マンホール・荒れた舗装などの路面の影響が大きく、車両の異常と断定するものではありません。
        </p>
      </Section>

      <Section title="できたこと・確かめたこと">
        <ul className="list-disc space-y-1 pl-5">
          <li>9 本の記録すべてで、サンプルの欠け・時刻の重複・書き込みエラーがないことを確認した。</li>
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
          <li>自宅の周辺 300 m の 1 秒分は、緯度・経度を消してから書き出している。このページのファイルにも入っていない（配る前に検査している）。</li>
          <li>データとこのページは非公開の S3 バケットに置き、期限付きの URL でだけ見られるようにしている。</li>
          <li>地図の背景（OpenFreeMap）を読み込むとき、表示している範囲がタイルのサーバーに伝わる。</li>
        </ul>
      </Section>
    </div>
  );
}
