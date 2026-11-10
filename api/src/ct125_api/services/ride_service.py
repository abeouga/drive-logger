"""走行の台帳・処理の記録・モデルを見る／変える（#16・#17）。

見るのはログインした人なら誰でも。変える（消す・戻す・完全に削除・公開する結果やモデルの切り替え）のは admin だけ。
台帳を書き換えたら、処理の Lambda に公開用の作り直しを頼む（公開用に書けるのはその Lambda だけ）。
"""

import logging
from collections.abc import Callable
from datetime import datetime

from ..domain import ledger as ledgermod
from ..domain.exceptions import (
    ForbiddenError,
    InvalidRequestError,
    LedgerConflictError,
    ModelNotFoundError,
    PurgeIncompleteError,
    RideNotFoundError,
)
from ..domain.user import User
from ..repositories.ride_files_repository import RideFilesRepository
from ..repositories.work_repository import LedgerWriteConflict, WorkRepository
from .pipeline_client import PipelineClient

MAX_ATTEMPTS = 3

# 誰がいつ完全に削除したかを、データ API のログ（CloudWatch Logs）に残す
log = logging.getLogger("ct125_api.purge")
log.setLevel(logging.INFO)


class RideService:
    def __init__(
        self,
        work: WorkRepository,
        pipeline: PipelineClient,
        files: RideFilesRepository | None = None,
        now: Callable[[], datetime] = ledgermod.utc_now,
    ) -> None:
        self._work = work
        self._pipeline = pipeline
        self._files = files
        self._now = now

    # ================================================================ 走行の一覧（#16）
    def list_rides(self, user: User, include_deleted: bool) -> list[dict]:
        if include_deleted:
            _require_admin(user)
        ledger = self._ledger()
        rides = []
        for ride_id, entry in sorted(ledger["rides"].items()):
            if not include_deleted and not ledgermod.shown_on_screen(entry):
                continue
            summary = self._work.read_summary(entry["published_run"], ride_id) if entry["published_run"] else None
            rides.append({
                "id": ride_id,
                "original_name": entry["original_name"],
                "kind": entry["kind"],
                "deleted": entry["deleted"],
                "deleted_at": entry["deleted_at"],
                "published_run": entry["published_run"],
                "summary": summary,
            })
        return rides

    def delete(self, user: User, ride_id: str) -> dict:
        _require_admin(user)
        ride_id = ledgermod.check_ride_id(ride_id)
        updated = self._change(lambda ledger: ledgermod.mark_deleted(ledger, ride_id, user.username, self._now()))
        self._pipeline.publish()
        return _state(updated, ride_id)

    def restore(self, user: User, ride_id: str) -> dict:
        _require_admin(user)
        ride_id = ledgermod.check_ride_id(ride_id)
        updated = self._change(lambda ledger: ledgermod.restore(ledger, ride_id, self._now()))
        self._pipeline.publish()
        return _state(updated, ride_id)

    def purge(self, user: User, ride_id: str, confirm_ride_id: str) -> dict:
        """ゴミ箱に入っている走行を完全に削除する（#82）。元に戻せない。

        順番：台帳の 1 件を除いて公開し直しを頼む → 処理の結果 → 生データ。
        途中で失敗しても、画面に消えかけの走行が出ないようにするため（画面は台帳から作る）。
        run.json とモデル（model.json の学習に使った走行）は記録なので書き換えない。消した走行の ID は、そこに残る。
        """
        _require_admin(user)
        ride_id = ledgermod.check_ride_id(ride_id)
        if confirm_ride_id != ride_id:
            raise InvalidRequestError(f"確かめの名前が走行の名前と違います。{ride_id} と打ち込んでください")
        if self._files is None:
            raise RuntimeError("走行のファイルを消す部品が組み立てられていません")
        removed: dict = {}

        def change(ledger: dict) -> dict:
            updated, entry = ledgermod.remove(ledger, ride_id, self._now())
            removed["entry"] = entry
            return updated

        self._change(change)
        self._pipeline.publish()
        runs = list(removed["entry"]["runs"])
        log.info("完全に削除を始めます：%s（%s が %s に）。台帳から除き、公開し直しを頼みました。処理の結果を消す処理：%s",
                 ride_id, user.username, ledgermod.iso(self._now()), ",".join(runs) or "なし")
        result_files = raw_files = 0
        step = "処理の結果"
        try:
            for run_id in runs:
                result_files += self._files.delete_results(run_id, ride_id)
            step = "生データ"
            raw_files = self._files.delete_raw(ride_id)
        except Exception as error:
            log.error("完全に削除が途中で止まりました：%s（%s を消している途中）。台帳からは除いてあります。残りは S3 で消してください：%s",
                      ride_id, step, error)
            raise PurgeIncompleteError(
                f"{ride_id} の{step}を消している途中で失敗しました。台帳と画面からは除いてあります。残ったファイルはデータ API のログを見て消してください（{error}）"
            ) from error
        log.info("完全に削除しました：%s（%s）。生データ %d ファイル、処理の結果 %d ファイル",
                 ride_id, user.username, raw_files, result_files)
        return {"ride_id": ride_id, "purged": True, "removed": {"raw_files": raw_files, "result_files": result_files, "runs": runs}}

    # ================================================================ 処理の記録（#17）
    def list_runs(self, user: User, ride_id: str) -> list[dict]:
        ride_id = ledgermod.check_ride_id(ride_id)
        entry = self._visible_entry(user, ride_id)
        runs = []
        for run_id in entry["runs"]:
            run = self._work.read_run(run_id)
            if run is None:
                continue
            result = next((r for r in run["rides"] if r["ride_id"] == ride_id), None)
            runs.append({
                "run_id": run_id,
                "action": run["action"],
                "created_at": run["started_at"],
                "finished_at": run["finished_at"],
                "where": run["where"],
                "commit": run["commit"],
                "model_version": run["model_version"],
                "status": result["status"] if result else run["status"],
                "error": (result or {}).get("error") or (run["error"] if run["status"] == "failed" and not result else None),
                "published": run_id == entry["published_run"],
            })
        return runs

    def set_published_run(self, user: User, ride_id: str, run_id: str) -> dict:
        _require_admin(user)
        ride_id = ledgermod.check_ride_id(ride_id)
        run_id = ledgermod.check_run_id(run_id)
        run = self._work.read_run(run_id)
        updated = self._change(lambda ledger: ledgermod.point_to_run(ledger, ride_id, run, self._now()))
        self._pipeline.publish()
        return _state(updated, ride_id)

    # ================================================================ モデル（#17）
    def list_models(self) -> dict:
        models = []
        for version in self._work.model_versions():
            record = self._work.read_model(version)
            models.append({
                "version": version,
                "created_at": record["created_at"] if record else None,
                "where": record["where"] if record else None,
                "commit": record["commit"] if record else None,
                "n_rides": len(record["train"]["rides"]) if record else None,
                "n_windows": record["train"]["n_windows"] if record else None,
                "has_record": record is not None,
            })
        return {"current": self._work.current_model(), "models": models}

    def model(self, version: str) -> dict:
        record = self._work.read_model(ledgermod.check_model_version(version))
        if record is None:
            raise ModelNotFoundError(f"モデル {version} の記録（model.json）がありません")
        return record

    def model_notes(self, version: str) -> str:
        notes = self._work.read_notes(ledgermod.check_model_version(version))
        if notes is None:
            raise ModelNotFoundError(f"モデル {version} のナレッジ（notes.md）がありません")
        return notes

    def use_model(self, user: User, version: str) -> dict:
        """今使うモデルを切り替える。全走行の点数付けし直しは処理の Lambda が行う（数分かかるので待たない）。"""
        _require_admin(user)
        version = ledgermod.check_model_version(version)
        if not self._work.model_exists(version):
            raise ModelNotFoundError(f"モデル {version} がありません")
        self._pipeline.use_model(version)
        return {"status": "accepted", "version": version}

    # ================================================================ 内部
    def _ledger(self) -> dict:
        ledger, _ = self._work.read_ledger()
        return ledger or {"schema": "ledger/1", "updated_at": None, "rides": {}}

    def _visible_entry(self, user: User, ride_id: str) -> dict:
        entry = self._ledger()["rides"].get(ride_id)
        # 画面に出さない走行は、admin でなければ「無い」ことにする
        if entry is None or (not ledgermod.shown_on_screen(entry) and not user.belongs_to(ledgermod.ADMIN_GROUP)):
            raise RideNotFoundError(f"{ride_id} は台帳にありません")
        return entry

    def _change(self, change: Callable[[dict], dict]) -> dict:
        for _ in range(MAX_ATTEMPTS):
            ledger, etag = self._work.read_ledger()
            if ledger is None:
                raise RideNotFoundError("台帳がまだありません")
            updated = change(ledger)
            try:
                self._work.write_ledger(updated, etag)
                return updated
            except LedgerWriteConflict:
                continue
        raise LedgerConflictError("台帳がほかの処理に続けて書き換えられました。読み直してやり直してください")


def _require_admin(user: User) -> None:
    if not user.belongs_to(ledgermod.ADMIN_GROUP):
        raise ForbiddenError("この操作は admin だけができます")


def _state(ledger: dict, ride_id: str) -> dict:
    entry = ledger["rides"][ride_id]
    return {"ride_id": ride_id, "deleted": entry["deleted"], "published_run": entry["published_run"], "kind": entry["kind"]}
