# 走行データのバケットを役割ごとに分ける（docs/data_flow_design.md 3.、#2 の決定 A）。
#   raw    生データの正本。書けるのはデバイス API だけ。保存期間なし
#   work   処理の結果と記録（runs/）、モデル（models/）、走行の台帳（ledger/）。書けるのは処理（Lambda・ローカル）と、台帳だけデータ API
#   public 画面が読む JSON・PNG（datasets/shared/）。書けるのは公開の仕組み（処理の Lambda）だけ
# どれも非公開・SSE-S3・HTTPS のみ・バージョニング（古い版は noncurrent_version_days 日）。今のバケット（s3.tf）は画面（webapp/）用に残す。

locals {
  data_roles = {
    raw    = "生データの正本（機器から届いた CSV と meta.json）"
    work   = "処理の結果と記録・モデル・走行の台帳"
    public = "画面が読む JSON・PNG（公開中の結果だけ）"
  }
  public_dataset_prefix = "datasets/"
}

resource "aws_s3_bucket" "role" {
  for_each = local.data_roles
  bucket   = "${var.bucket_prefix}-${each.key}-${data.aws_caller_identity.current.account_id}"
  # 中身があるバケットは terraform destroy でも消えない（生データを誤って消さないため。ほかの 2 つも同じにそろえる）
  force_destroy = false

  tags = {
    Role        = each.key
    Description = each.value
  }
}

resource "aws_s3_bucket_ownership_controls" "role" {
  for_each = aws_s3_bucket.role
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACL を無効にする
  }
}

resource "aws_s3_bucket_public_access_block" "role" {
  for_each                = aws_s3_bucket.role
  bucket                  = each.value.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "role" {
  for_each = aws_s3_bucket.role
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3（追加料金なし）
    }
  }
}

resource "aws_s3_bucket_versioning" "role" {
  for_each = aws_s3_bucket.role
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "role" {
  for_each   = aws_s3_bucket.role
  bucket     = each.value.id
  depends_on = [aws_s3_bucket_versioning.role]

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "role_bucket" {
  for_each = aws_s3_bucket.role

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      each.value.arn,
      "${each.value.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "role" {
  for_each   = aws_s3_bucket.role
  bucket     = each.value.id
  policy     = data.aws_iam_policy_document.role_bucket[each.key].json
  depends_on = [aws_s3_bucket_public_access_block.role]
}
