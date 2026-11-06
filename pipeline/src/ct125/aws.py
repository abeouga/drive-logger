# -*- coding: utf-8 -*-
"""S3 へのアップロードと署名付き URL の発行（計画書フェーズ 4、11.）。

- バケットは公開しない（パブリックアクセスブロック有効のまま）。配信は署名付き GET URL。
- 認証情報はリポジトリに置かず、~/.aws のプロファイル（config/default.yaml の aws.profile）を使う。
- 位置情報を含む processed/ と site/ は、自宅マスク（config/local.yaml）を適用してからアップロードする。
  未適用のときは upload_ride が例外を出す（--allow-unmasked で明示的に許可した場合だけ通す）。
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

import boto3
from botocore.config import Config

RAW_FILES = ["accel.csv", "gps.csv", "events.csv", "status.csv", "meta.json"]
PROCESSED_FILES = ["windows.parquet", "scored.parquet"]


class UnmaskedError(RuntimeError):
    """自宅マスクが適用されていない状態で位置情報付きのファイルを上げようとした。"""


def make_session(acfg: dict) -> boto3.Session:
    return boto3.Session(profile_name=acfg.get("profile") or None, region_name=acfg.get("region") or None)


def make_s3(session: boto3.Session):
    """S3 クライアント。署名付き URL が SigV4 ＋リージョン付きのホスト名
    （<bucket>.s3.<region>.amazonaws.com）で作られるようにする。
    既定のままだと SigV2 ＋共通エンドポイントになり、作ったばかりのバケットでは 307 リダイレクトで開けない。"""
    region = session.region_name
    return session.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com" if region else None,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}, retries={"total_max_attempts": 3, "mode": "standard"}),
    )


def bucket_region(session: boto3.Session) -> str:
    region = session.region_name
    if not region:
        raise RuntimeError("リージョンが決まっていません。プロファイルの region か config の aws.region を設定してください")
    return region


def create_bucket(s3, bucket: str, region: str) -> None:
    """バケットを作り、パブリックアクセスブロックを有効にし、既定の暗号化（SSE-S3）を付ける。既にあれば何もしない。"""
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except s3.exceptions.ClientError as e:  # 404 = ない、403 = 他人のもの
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise
    kwargs = {"Bucket": bucket}
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**kwargs)
    s3.get_waiter("bucket_exists").wait(Bucket=bucket)
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True},
    )
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})


def _content_type(path: Path) -> str:
    if path.suffix == ".parquet":
        return "application/vnd.apache.parquet"
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def upload_files(s3, bucket: str, pairs: list[tuple[Path, str]], verbose: bool = True) -> list[str]:
    keys = []
    for local, key in pairs:
        if not local.exists():
            continue
        s3.upload_file(str(local), bucket, key, ExtraArgs={"ContentType": _content_type(local)})
        keys.append(key)
        if verbose:
            print(f"  s3://{bucket}/{key}  ({local.stat().st_size / 1024:.0f} KB)")
    return keys


def ride_pairs(root: Path, ride_id: str, parts: tuple[str, ...] = ("raw", "processed", "site")) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    if "raw" in parts:
        pairs += [(root / "data" / "raw" / ride_id / f, f"raw/{ride_id}/{f}") for f in RAW_FILES]
    if "processed" in parts:
        pairs += [(root / "data" / "processed" / ride_id / f, f"processed/{ride_id}/{f}") for f in PROCESSED_FILES]
    if "site" in parts:
        pairs.append((root / "web" / ride_id / "index.html", f"site/{ride_id}/index.html"))
    return pairs


def model_pairs(root: Path) -> list[tuple[Path, str]]:
    pairs = []
    for d in sorted((root / "data" / "models").glob("*")):
        for f in ("baseline.json", "isolation_forest.pkl"):
            pairs.append((d / f, f"models/{d.name}/{f}"))
    return pairs


def upload_ride(s3, bucket: str, root: Path, ride_id: str, parts: tuple[str, ...], masked: bool, allow_unmasked: bool = False, verbose: bool = True) -> list[str]:
    """1 走行分を raw/ processed/ site/ へ。位置情報を含む processed/ と site/ はマスク適用時のみ。"""
    if not masked and not allow_unmasked and any(p in parts for p in ("processed", "site")):
        raise UnmaskedError(
            "自宅マスクが未適用です（config/local.yaml に home の座標がない）。processed/ と site/ はアップロードしません。"
            "座標を書いて process --all → score → render を再実行してください（非公開のまま上げるだけなら --allow-unmasked）"
        )
    if verbose:
        print(f"{ride_id}: {', '.join(parts)} → s3://{bucket}/")
    return upload_files(s3, bucket, ride_pairs(root, ride_id, parts), verbose)


def presigned_site_url(s3, bucket: str, ride_id: str, expires_hours: float) -> str:
    """site/<ride_id>/index.html の署名付き GET URL。上限 7 日（168 時間）。

    注意：一時的な認証情報（aws login のセッション、assumed role）で発行した URL は、その認証情報の期限で失効する。
    7 日有効にしたいときは、長期の認証情報（IAM ユーザーのアクセスキー）を持つプロファイルで発行する。
    """
    expires = int(min(max(expires_hours, 0.1), 168) * 3600)
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": f"site/{ride_id}/index.html", "ResponseContentType": "text/html; charset=utf-8"},
        ExpiresIn=expires,
    )


def list_keys(s3, bucket: str, prefix: str = "") -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    return list(paginator.paginate(Bucket=bucket, Prefix=prefix).search("Contents[].Key") or [])
