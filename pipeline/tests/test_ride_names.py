# -*- coding: utf-8 -*-
"""走行の名前（records.name_rides。#96）：「YYYY/MM/DDの走行」と、同じ日の (1)(2)。一度付けた名前は変えない。"""
from __future__ import annotations

from datetime import datetime, timezone

from ct125 import records

NOW = datetime(2026, 11, 11, 3, 0, 0, tzinfo=timezone.utc)


def jst_ms(text: str) -> int:
    """日本時間の「2026-11-02 14:00:00」→ UNIX ミリ秒。"""
    return int(datetime.fromisoformat(text + "+09:00").timestamp() * 1000)


def ledger_of(*ride_ids: str, names: dict[str, str] | None = None) -> dict:
    ledger = records.empty_ledger(NOW)
    for ride_id in ride_ids:
        entry = records.new_entry(ride_id, None)
        entry["name"] = (names or {}).get(ride_id)
        ledger["rides"][ride_id] = entry
    return ledger


def names_of(ledger: dict) -> dict[str, str]:
    return {ride_id: entry["name"] for ride_id, entry in ledger["rides"].items()}


def test_same_day_rides_are_numbered_in_the_order_they_started():
    # 3 本とも 11/09 に届いたが、走ったのは 11/02（GPS の時刻）。走行 ID の順と、走り始めた順は違う
    starts = {
        "ride_20261109_030109": jst_ms("2026-11-02 15:00:00"),
        "ride_20261109_030200": jst_ms("2026-11-02 09:30:00"),
        "ride_20261109_030300": jst_ms("2026-11-02 12:00:00"),
    }
    named = records.name_rides(ledger_of(*starts), lambda ride_id, entry: starts[ride_id])
    assert names_of(named) == {
        "ride_20261109_030200": "2026/11/02の走行",
        "ride_20261109_030300": "2026/11/02の走行(1)",
        "ride_20261109_030109": "2026/11/02の走行(2)",
    }


def test_date_is_the_japanese_day_the_ride_started():
    # UTC では 11/01 だが、日本時間では 11/02 の 0 時台
    start = int(datetime(2026, 11, 1, 15, 30, tzinfo=timezone.utc).timestamp() * 1000)
    named = records.name_rides(ledger_of("ride_20261109_030109"), lambda ride_id, entry: start)
    assert names_of(named) == {"ride_20261109_030109": "2026/11/02の走行"}


def test_ride_without_gps_is_named_by_the_day_it_arrived():
    starts = {"ride_20261109_030109": None, "ride_20261110_080000": jst_ms("2026-11-09 07:00:00")}
    named = records.name_rides(ledger_of(*starts), lambda ride_id, entry: starts[ride_id])
    # GPS なしは走行 ID の日時（11/09 03:01、届いた時刻）で、11/09 07:00 に走り始めた走行より先
    assert names_of(named) == {"ride_20261109_030109": "2026/11/09の走行", "ride_20261110_080000": "2026/11/09の走行(1)"}


def test_names_are_not_changed_once_given():
    ledger = ledger_of("ride_20261109_030109", names={"ride_20261109_030109": "2026/11/02の走行"})
    named = records.name_rides(ledger, lambda ride_id, entry: jst_ms("2026-11-03 10:00:00"))
    assert named is ledger  # 名前の無い走行が無ければ、台帳はそのまま


def test_a_ride_that_started_earlier_but_arrived_later_gets_the_next_number():
    ledger = ledger_of("ride_20261109_030109", names={"ride_20261109_030109": "2026/11/02の走行"})
    ledger = {**ledger, "rides": {**ledger["rides"], "ride_20261111_090000": records.new_entry("ride_20261111_090000", None)}}
    named = records.name_rides(ledger, lambda ride_id, entry: jst_ms("2026-11-02 06:00:00"))  # 11/02 の朝、前の走行より早く走った
    assert names_of(named) == {"ride_20261109_030109": "2026/11/02の走行", "ride_20261111_090000": "2026/11/02の走行(1)"}


def test_numbers_continue_after_the_largest_one_on_that_day():
    # (1) の走行を完全に削除した後でも、残っている一番大きい番号の続きにする（消した走行の名前を別の走行に使い回さない）
    ledger = ledger_of("ride_20261109_030109", "ride_20261109_040000", "ride_20261111_090000",
                       names={"ride_20261109_030109": "2026/11/02の走行", "ride_20261109_040000": "2026/11/02の走行(2)"})
    named = records.name_rides(ledger, lambda ride_id, entry: jst_ms("2026-11-02 18:00:00"))
    assert names_of(named)["ride_20261111_090000"] == "2026/11/02の走行(3)"


def test_old_ride_id_uses_the_received_time_or_keeps_the_id():
    ledger = ledger_of("ride_004", "ride_005")
    ledger["rides"]["ride_004"]["received_at"] = "2026-11-07T14:35:07Z"  # 日本時間 11/07 23:35
    named = records.name_rides(ledger)
    assert names_of(named) == {"ride_004": "2026/11/07の走行", "ride_005": "ride_005"}


def test_record_run_names_new_rides_and_puts_the_name_after_the_ride_id():
    run = {"run_id": "20261111T030000Z-abcdef", "rides": [records.ride_result("ride_20261111_020000", "ride", {}, 10, 0)]}
    ledger = records.record_run(records.empty_ledger(NOW), run, {}, True, NOW, lambda ride_id, entry: jst_ms("2026-11-10 21:00:00"))
    entry = ledger["rides"]["ride_20261111_020000"]
    assert entry["name"] == "2026/11/10の走行"
    assert list(entry)[:2] == ["ride_id", "name"]
