# -*- coding: utf-8 -*-
"""rides.json（走行一覧）の 1 件を差し替える。

複数の走行が同時に処理されても一覧が壊れないよう、S3 の条件付き書き込みを使う：
読んだときの ETag のまま変わっていなければ書く。変わっていたら読み直してやり直す。
"""
from __future__ import annotations

from ..export import rides_document
from .s3_store import S3Store, WriteConflictError

MAX_ATTEMPTS = 5


def upsert_summary(document: dict | None, summary: dict) -> dict:
    """一覧に summary を入れる（同じ ID があれば置き換える）。元の document は変えない。"""
    rides = list((document or {}).get("rides", []))
    others = [ride for ride in rides if ride["id"] != summary["id"]]
    return rides_document(others + [summary])


def save_summary(store: S3Store, key: str, summary: dict) -> dict:
    """S3 の rides.json に summary を入れて保存し、保存した中身を返す。"""
    for _ in range(MAX_ATTEMPTS):
        current, etag = store.read_json(key)
        updated = upsert_summary(current, summary)
        try:
            store.write_json(key, updated, expected_etag=etag, must_not_exist=current is None)
            return updated
        except WriteConflictError:
            continue  # ほかの走行の処理が先に書いた。読み直してやり直す
    raise RuntimeError(f"{key} を {MAX_ATTEMPTS} 回続けて書けませんでした")
