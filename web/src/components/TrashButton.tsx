// 走行をゴミ箱へ移すボタン（admin だけに出す）。走行カードと走行の画面で同じ形・同じ確かめの文を使う。
import { TbTrash } from "react-icons/tb";
import { deleteRide } from "../lib/data";
import ActionButton from "./ActionButton";

export default function TrashButton({ rideId, onDone, className = "" }: { rideId: string; onDone?: () => void; className?: string }) {
  return (
    <ActionButton
      label="ゴミ箱へ移す"
      icon={<TbTrash aria-hidden className="size-[18px]" />}
      tone="danger"
      className={className}
      confirmText={`${rideId} を画面と学習から外します。生データは残り、ゴミ箱から戻せます。よろしいですか？`}
      onRun={async () => {
        await deleteRide(rideId);
        onDone?.();
      }}
    />
  );
}
