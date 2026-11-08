# -*- coding: utf-8 -*-
"""S3 へのアップロード（ローカルの CLI の `upload`）と、S3 クライアントの作り方。

- バケットは公開しない（パブリックアクセスブロック有効のまま）。バケットそのものは Terraform（infra/）が作る。
- 認証情報はリポジトリに置かず、~/.aws のプロファイル（config/default.yaml の aws.profile）を使う。
"""
from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

# 生データとして上げるファイル（contracts/upload/upload.json の files.allowed）。無いファイルは飛ばす
RAW_FILES = ["accel.csv", "gps.csv", "events.csv", "status.csv", "meta.json", "notes.md", "memo.txt", "readme.txt"]
# 生データを上げ終わった印。これが置かれると、AWS の Lambda がその走行を処理する（ct125/cloud/）
UPLOAD_COMPLETE_MARKER = "upload_complete.json"
PROCESSED_FILES = ["windows.parquet", "scored.parquet"]


def make_session(acfg: dict) -> boto3.Session:
    return boto3.Session(profile_name=acfg.get("profile") or None, region_name=acfg.get("region") or None)


def make_s3(session: boto3.Session):
    """S3 クライアント。SigV4 ＋リージョン付きのエンドポイント（<bucket>.s3.<region>.amazonaws.com）にする。

    既定のままだと SigV2 ＋共通エンドポイントになり、作ったばかりのバケットでは 307 リダイレクトが返ることがある。
    """
    region = session.region_name
    return session.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com" if region else None,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}, retries={"total_max_attempts": 3, "mode": "standard"}),
    )


def content_type_of(path: Path) -> str:
    fixed = {
        ".parquet": "application/vnd.apache.parquet",
        ".json": "application/json; charset=utf-8",  # 日本語のメモを含むので文字コードを明示
        ".png": "image/png",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }
    return fixed.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def upload_files(s3, bucket: str, pairs: list[tuple[Path, str]], verbose: bool = True) -> list[str]:
    keys = []
    for local, key in pairs:
        if not local.exists():
            continue
        s3.upload_file(str(local), bucket, key, ExtraArgs={"ContentType": content_type_of(local)})
        keys.append(key)
        if verbose:
            print(f"  s3://{bucket}/{key}  ({local.stat().st_size / 1024:.0f} KB)")
    return keys


def ride_pairs(root: Path, ride_id: str, parts: tuple[str, ...] = ("raw", "processed")) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    if "raw" in parts:
        pairs += [(root / "data" / "raw" / ride_id / f, f"raw/{ride_id}/{f}") for f in RAW_FILES]
    if "processed" in parts:
        pairs += [(root / "data" / "processed" / ride_id / f, f"processed/{ride_id}/{f}") for f in PROCESSED_FILES]
    return pairs


def model_pairs(root: Path) -> list[tuple[Path, str]]:
    pairs = []
    for d in sorted((root / "data" / "models").glob("*")):
        for f in ("baseline.json", "isolation_forest.pkl"):
            pairs.append((d / f, f"models/{d.name}/{f}"))
    return pairs


def upload_ride(s3, bucket: str, root: Path, ride_id: str, parts: tuple[str, ...], verbose: bool = True) -> list[str]:
    """1 走行分を raw/ と processed/ へ。raw/ を上げたら、最後に完了の印を置く（AWS の処理が動く）。"""
    if verbose:
        print(f"{ride_id}: {', '.join(parts)} → s3://{bucket}/")
    keys = upload_files(s3, bucket, ride_pairs(root, ride_id, parts), verbose)
    raw_keys = [k for k in keys if k.startswith(f"raw/{ride_id}/")]
    if raw_keys:
        keys.append(mark_upload_complete(s3, bucket, ride_id, raw_keys, verbose))
    return keys


def mark_upload_complete(s3, bucket: str, ride_id: str, raw_keys: list[str], verbose: bool = True) -> str:
    """raw/<走行>/ に「上げ終わった」印を最後に置く。AWS 側はこれを合図に処理を始める。"""
    key = f"raw/{ride_id}/{UPLOAD_COMPLETE_MARKER}"
    body = {"ride_id": ride_id, "files": [k.rsplit("/", 1)[-1] for k in raw_keys], "uploaded_at": datetime.now(timezone.utc).isoformat()}
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(body).encode("utf-8"), ContentType="application/json")
    if verbose:
        print(f"  s3://{bucket}/{key}  （処理の合図）")
    return key
