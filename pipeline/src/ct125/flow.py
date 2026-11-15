# -*- coding: utf-8 -*-
"""処理の流れ（1 本）。ローカルの CLI と AWS の Lambda の両方から、同じものを呼ぶ（docs/data_flow_design.md 5.〜8.）。

process：生データ → 前処理 → 分類 → 今のモデルで点数付け → 画面用の書き出し → 作業用に保存 → 処理の記録 → 台帳
retrain：台帳で「学習に使う」走行だけで学習 → 新しいモデルの版 → 全走行を点数付けし直す → 作業用に保存 → 記録 → 台帳
publish：台帳が指す結果から、公開用（画面が読む場所）を作り直す
use_model：今使うモデルを選んだ版にし、全走行を点数付けし直して公開する（画面の「このモデルに切り替える」）
evaluate：学習に使う走行を 1 本ずつ抜いて学習し、抜いた走行に点数を付ける（確かめ。どこにも書かない）

違うのは「どこで動いたか（where）」と「公開してよいか」だけ。公開用に書けるのは Lambda だけで、
ローカルの処理は作業用に結果を置くだけ（公開は Lambda に頼む）。
"""
from __future__ import annotations

import io as stdio
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import classify as classifymod
from . import evaluate as evaluatemod
from . import export, io, processing, records
from .records import RIDE_ID_PATTERN
from .model import anomaly_rule, apply_models, fit_models, training_mask
from .models import ModelStore
from .storage import Area, WriteConflictError

LEDGER = "ledger/rides.json"
PUBLISHED = "ledger/published.json"  # 公開用に今どの結果を出しているか（公開の仕組みだけが書く）
UPLOAD_COMPLETE = "upload_complete.json"
MAX_ATTEMPTS = 5


class PublishNotAllowedError(RuntimeError):
    """公開用の場所が無い（ローカルの処理は公開しない。公開は処理の Lambda に頼む）。"""


@dataclass(frozen=True)
class Places:
    """3 つの場所。public はローカルの処理では None（公開用に書けない）。"""

    raw: Area
    work: Area
    public: Area | None


@dataclass(frozen=True)
class _Analyzed:
    pre: processing.Preprocessed
    kind: str
    kind_metrics: dict


class Pipeline:
    def __init__(self, cfg: dict, places: Places, where: str, commit: str | None = None, log: Callable[[str], None] = print, clock: Callable = records.utc_now) -> None:
        self._cfg = cfg
        self._places = places
        self._where = where
        self._commit = commit
        self._log = log
        self._clock = clock
        self._models = ModelStore(places.work)

    # ================================================================ 新しい走行（推論だけ）
    def process(self, ride_ids: list[str], publish: bool) -> dict:
        run = self._start("process")
        markers: dict[str, dict | None] = {}
        try:
            trained = self._models.load_current()
            run["model_version"] = trained.version
            for ride_id in ride_ids:
                markers[ride_id] = self._marker(ride_id)
                run["rides"].append(self._process_one(run["run_id"], ride_id, trained))
        except Exception as error:
            self._fail(run, error)
            raise
        return self._finish(run, markers, publish)

    def _process_one(self, run_id: str, ride_id: str, trained) -> dict:
        try:
            analyzed = self._analyze(ride_id)
            scored = self._score(analyzed.pre.windows, trained.baseline, trained.forest, trained.forest_info)
            return self._save_ride(run_id, analyzed, scored, trained.version, trained.forest_info)
        except Exception as error:  # 1 走行の失敗は記録して、ほかの走行は続ける
            self._log(f"{ride_id}: 失敗 {type(error).__name__}: {error}")
            return records.ride_result(ride_id, error=f"{type(error).__name__}: {error}")

    # ================================================================ 学習し直し（全走行）
    def retrain(self, publish: bool) -> dict:
        run = self._start("retrain")
        version = records.new_model_version(self._clock())
        run["model_version"] = version
        markers: dict[str, dict | None] = {}
        try:
            ledger = self._read_ledger()
            analyzed: dict[str, _Analyzed] = {}
            failed: dict[str, str] = {}
            for ride_id in self.ride_ids():
                markers[ride_id] = self._marker(ride_id)
                try:
                    analyzed[ride_id] = self._analyze(ride_id)
                except Exception as error:
                    failed[ride_id] = f"{type(error).__name__}: {error}"
                    self._log(f"{ride_id}: 失敗 {failed[ride_id]}")

            train_ids, excluded = self._choose_training(analyzed, failed, ledger)
            if not train_ids:
                raise ValueError("学習に使える走行がありません（停車・実走で、消していない走行）")
            train_windows = pd.concat([analyzed[ride_id].pre.windows for ride_id in train_ids], ignore_index=True)
            baseline, forest, forest_info = fit_models(train_windows, self._cfg.get("model", {}))

            for ride_id in sorted(analyzed):
                scored = self._score(analyzed[ride_id].pre.windows, baseline, forest, forest_info)
                run["rides"].append(self._save_ride(run["run_id"], analyzed[ride_id], scored, version, forest_info))
            run["rides"] += [records.ride_result(ride_id, error=error) for ride_id, error in sorted(failed.items())]
            run["rides"].sort(key=lambda result: result["ride_id"])

            record = self._model_record(version, run["run_id"], analyzed, train_ids, excluded, train_windows, baseline, forest, forest_info)
            self._models.save(version, baseline, forest, record, records.model_notes(record))
            self._log(f"モデル {version}：学習した走行 {len(train_ids)}、窓 {record['train']['n_windows']}、使わなかった走行 {len(excluded)}")
        except Exception as error:
            self._fail(run, error)
            raise
        return self._finish(run, markers, publish, switch_model=True)

    # ================================================================ モデルの切り替え
    def use_model(self, version: str) -> dict:
        """今使うモデルを version にし、全走行をそのモデルで点数付けし直して公開する。"""
        if self._places.public is None:
            raise PublishNotAllowedError("モデルの切り替えは処理の Lambda だけが行います")
        self._models.load(version)  # 無い版・ライブラリの版が合わない版は、切り替える前に止める
        self._models.set_current(version)
        self._log(f"今使うモデルを {version} にしました。全走行を点数付けし直します")
        return self.process(self.ride_ids(), publish=True)

    # ================================================================ 確かめ（読むだけ）
    def evaluate(self, top_n: int = 20) -> evaluatemod.Evaluation:
        """retrain と同じ決まりで学習に使う走行を選び、1 走行ずつ抜いて確かめる。モデルの版・処理の記録・台帳は書かない。"""
        ledger = self._read_ledger()
        analyzed: dict[str, _Analyzed] = {}
        failed: dict[str, str] = {}
        for ride_id in self.ride_ids():
            try:
                analyzed[ride_id] = self._analyze(ride_id)
            except Exception as error:
                failed[ride_id] = f"{type(error).__name__}: {error}"
                self._log(f"{ride_id}: 失敗 {failed[ride_id]}")
        train_ids, _ = self._choose_training(analyzed, failed, ledger)
        windows = {ride_id: analyzed[ride_id].pre.windows for ride_id in train_ids}
        return evaluatemod.leave_one_ride_out(windows, self._cfg.get("model", {}), self._cfg.get("stop_speed_kmh", 5.0), top_n)

    def ride_ids(self) -> list[str]:
        """生データの場所にある走行（走行 ID の形のフォルダーだけ。受け付けの記録などは除く）。"""
        return [name for name in self._places.raw.folders() if RIDE_ID_PATTERN.fullmatch(name)]

    def _choose_training(self, analyzed: dict[str, _Analyzed], failed: dict[str, str], ledger: dict) -> tuple[list[str], list[dict]]:
        train, excluded = [], []
        for ride_id in sorted(set(analyzed) | set(failed)):
            if ride_id in failed:
                excluded.append({"ride_id": ride_id, "reason": "failed"})
                continue
            deleted = bool(ledger["rides"].get(ride_id, {}).get("deleted", False))
            use, reason = classifymod.used_for_training(analyzed[ride_id].kind, deleted, self._cfg)
            if use:
                train.append(ride_id)
            else:
                excluded.append({"ride_id": ride_id, "reason": reason})
        return train, excluded

    def _model_record(self, version: str, run_id: str, analyzed, train_ids, excluded, train_windows, baseline, forest, forest_info) -> dict:
        mask = training_mask(train_windows)
        scored_train = self._score(train_windows[mask], baseline, forest, forest_info)
        train = [{"ride_id": ride_id, "kind": analyzed[ride_id].kind, "n_windows": int(training_mask(analyzed[ride_id].pre.windows).sum())} for ride_id in train_ids]
        summary = {
            "baseline_bins": len(baseline["bins"]),
            "baseline_n_train": int(baseline["n_train"]),
            "n_anomaly_z": int(scored_train["is_anomaly_z"].sum()),
            "n_anomaly_if": int(scored_train["is_anomaly_if"].sum()),
            "n_anomaly_sif": int(scored_train["is_anomaly_sif"].sum()),
        }
        return records.model_record(version, self._clock(), self._where, self._commit, run_id, self._cfg, train, excluded, summary, forest_info)

    # ================================================================ 公開
    def publish(self, run_id: str | None = None) -> dict:
        """台帳が指す結果から公開用を作り直す。run_id を渡すと、先にその処理の結果を「公開中」にする（学習し直しならモデルも切り替える）。"""
        if self._places.public is None:
            raise PublishNotAllowedError("公開用の場所がありません。公開は処理の Lambda に頼んでください（python -m ct125 publish）")
        if run_id:
            run = self._places.work.read_json(f"runs/{run_id}/run.json")
            if run is None:
                raise FileNotFoundError(f"処理 {run_id} の記録がありません")
            if run["action"] == "retrain":
                if run["status"] != "succeeded":
                    raise ValueError(f"処理 {run_id} は失敗しているので公開できません：{run['error']}")
                self._models.set_current(run["model_version"])
            self._update_ledger(lambda ledger: records.point_to_run(ledger, run, self._clock(), self._start_ms))
        if records.needs_names(self._read_ledger()):  # 名前を足す前からある走行に、ここで 1 回だけ名前を付ける
            self._update_ledger(lambda ledger: records.name_rides(ledger, self._start_ms))
        for _ in range(MAX_ATTEMPTS):
            ledger, etag = self._places.work.read_json_tagged(LEDGER)
            result = self._publish_view(ledger or records.empty_ledger(self._clock()))
            _, etag_after = self._places.work.read_json_tagged(LEDGER)
            if etag_after == etag:  # 作り直している間に台帳が変わっていなければ終わり（変わっていたら、新しい台帳で作り直す）
                return result
        raise RuntimeError(f"台帳が {MAX_ATTEMPTS} 回続けて書き換わったので、公開を終えられませんでした")

    def _publish_view(self, ledger: dict) -> dict:
        public, work = self._places.public, self._places.work
        published = (work.read_json(PUBLISHED) or {}).get("rides", {})
        visible = {
            ride_id: entry["published_run"]
            for ride_id, entry in sorted(ledger["rides"].items())
            if entry["published_run"] and classifymod.shown_on_screen(entry["kind"], entry["deleted"], self._cfg)
        }
        summaries, copied = [], []
        existing = public.keys()  # 公開の場所にある今のファイル（生波形は分の数だけあるので、名前を一覧から探す）
        for ride_id, run_id in visible.items():
            base = f"runs/{run_id}/rides/{ride_id}/"
            summary = work.read_json(base + "summary.json")
            if summary is None:
                raise FileNotFoundError(f"{work.key(base)}summary.json がありません")
            summaries.append(summary)
            if published.get(ride_id) != run_id:
                names = []
                for key in work.keys(base + "app/"):
                    name = key.rsplit("/", 1)[-1]
                    public.put(name, work.get(key))
                    names.append(name)
                for name in export.ride_output_files(ride_id, existing):
                    if name not in names:
                        public.delete(name)
                copied.append(ride_id)
        removed = [ride_id for ride_id in published if ride_id not in visible]
        for ride_id in removed:
            for name in export.ride_output_files(ride_id, existing):
                public.delete(name)
        public.write_json("rides.json", export.rides_document(summaries, {ride_id: ledger["rides"][ride_id].get("name") or ride_id for ride_id in visible}))
        work.write_json(PUBLISHED, {"published_at": records.iso(self._clock()), "rides": visible})
        self._log(f"公開：{len(visible)} 走行（入れ替え {len(copied)}、外した {len(removed)}）")
        return {"n_rides": len(visible), "copied": copied, "removed": removed}

    # ================================================================ 共通
    def _start(self, action: str) -> dict:
        started = self._clock()
        run = records.start_run(records.new_run_id(started), action, self._where, self._commit, self._cfg, started)
        self._log(f"処理 {run['run_id']}（{action}、{self._where}）を始めます")
        return run

    def _fail(self, run: dict, error: Exception) -> None:
        failed = records.finish_run(run, self._clock(), error=f"{type(error).__name__}: {error}")
        self._save_run(failed)
        self._log(f"処理 {run['run_id']} は失敗しました：{failed['error']}")

    def _finish(self, run: dict, markers: dict, publish: bool, switch_model: bool = False) -> dict:
        run = records.finish_run(run, self._clock())
        self._save_run(run)
        # 学習し直しは全部が成功したときだけ公開する。新しい走行は、成功した走行だけを公開する
        publish_now = publish and (run["status"] == "succeeded" or not switch_model)
        self._update_ledger(lambda ledger: records.record_run(ledger, run, markers, publish_now, self._clock(), self._start_ms))
        result = {"run_id": run["run_id"], "action": run["action"], "status": run["status"], "error": run["error"], "model_version": run["model_version"], "rides": run["rides"]}
        if publish_now:
            if switch_model:
                self._models.set_current(run["model_version"])
            result["published"] = self.publish()
        return result

    def _analyze(self, ride_id: str) -> _Analyzed:
        with tempfile.TemporaryDirectory(prefix="ct125-") as tmp:
            self._download_raw(ride_id, Path(tmp))
            ride = io.load_ride(ride_id, tmp)
        pre = processing.preprocess(ride, self._cfg)
        kind, metrics = classifymod.classify(pre.windows, self._cfg)
        self._log(processing.describe(pre) + f", 分類 {kind}")
        return _Analyzed(pre, kind, metrics)

    def _download_raw(self, ride_id: str, dest: Path) -> None:
        folder = dest / ride_id
        folder.mkdir(parents=True)
        for relative in self._places.raw.keys(f"{ride_id}/"):
            name = relative[len(ride_id) + 1:]
            if name and "/" not in name:
                (folder / name).write_bytes(self._places.raw.get(relative))

    def _marker(self, ride_id: str) -> dict | None:
        return self._places.raw.read_json(f"{ride_id}/{UPLOAD_COMPLETE}")

    def _score(self, windows: pd.DataFrame, baseline: dict, forest, forest_info: dict) -> pd.DataFrame:
        return apply_models(windows, baseline, forest, self._cfg.get("model", {}), self._cfg.get("stop_speed_kmh", 5.0), forest_info)

    def _save_ride(self, run_id: str, analyzed: _Analyzed, scored: pd.DataFrame, model_version: str, forest_info: dict) -> dict:
        pre = analyzed.pre
        rule = anomaly_rule(self._cfg.get("model", {}), forest_info)
        summary, files = export.ride_files(scored, pre.accel, pre.memo, model_version, rule)
        base = f"runs/{run_id}/rides/{pre.ride_id}/"
        work = self._places.work
        work.put(base + "windows.parquet", _parquet(pre.windows))
        work.put(base + "scored.parquet", _parquet(scored))
        work.write_json(base + "summary.json", summary)
        for name, data in files.items():
            work.put(base + "app/" + name, data)
        return records.ride_result(pre.ride_id, analyzed.kind, analyzed.kind_metrics, int(len(scored)), int(summary["n_anomalies"]))

    def _start_ms(self, ride_id: str, entry: dict) -> int | None:
        """走り始めの時刻（要約の start_ms。GPS なしは None）。公開中の結果、無ければ新しい処理の結果から読む（名前の日付に使う）。"""
        for run_id in dict.fromkeys([entry.get("published_run"), *entry.get("runs", [])]):
            if run_id:
                summary = self._places.work.read_json(f"runs/{run_id}/rides/{ride_id}/summary.json")
                if summary is not None:
                    return summary.get("start_ms")
        return None

    def _save_run(self, run: dict) -> None:
        self._places.work.write_json(f"runs/{run['run_id']}/run.json", run)

    def _read_ledger(self) -> dict:
        return self._places.work.read_json(LEDGER) or records.empty_ledger(self._clock())

    def _update_ledger(self, change: Callable[[dict], dict]) -> dict:
        """台帳を条件付きで書き換える（ほかの処理が先に書いていたら、読み直してやり直す）。"""
        work = self._places.work
        for _ in range(MAX_ATTEMPTS):
            ledger, etag = work.read_json_tagged(LEDGER)
            updated = change(ledger or records.empty_ledger(self._clock()))
            try:
                work.write_json_if(LEDGER, updated, etag)
                return updated
            except WriteConflictError:
                continue
        raise RuntimeError(f"台帳を {MAX_ATTEMPTS} 回続けて書けませんでした")


def _parquet(frame: pd.DataFrame) -> bytes:
    buffer = stdio.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()
