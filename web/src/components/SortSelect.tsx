// 並べ替えの選択。選択肢と今の値を受け取るだけなので、ほかの一覧でも使える
type Option<K extends string> = { value: K; label: string };

export default function SortSelect<K extends string>({
  value,
  options,
  onChange,
  label = "並べ替え",
}: {
  value: K;
  options: readonly Option<K>[];
  onChange: (value: K) => void;
  label?: string;
}) {
  return (
    <label className="inline-flex items-center gap-2 text-[13px] font-bold text-ink-2">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as K)}
        className="field font-normal"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
