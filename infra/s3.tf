# 走行データ（raw / processed / models）と走行ページ（site）を置く非公開バケット。
# バケット自体は公開しない。Web アプリは CloudFront（OAC）経由で webapp/ だけを配る（cloudfront.tf）。

resource "aws_s3_bucket" "data" {
  bucket = "${var.bucket_prefix}-${data.aws_caller_identity.current.account_id}"
  # 生データを誤って消さないよう、中身があるバケットは terraform destroy でも消えない
  force_destroy = false
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ACL を無効にする
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3（追加料金なし）
    }
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket     = aws_s3_bucket.data.id
  depends_on = [aws_s3_bucket_versioning.data]

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

# バケットポリシー：HTTPS 以外を拒否し、CloudFront（この配信だけ）に webapp/ の読み取りを許す
data "aws_iam_policy_document" "data_bucket" {
  statement {
    sid       = "AllowCloudFrontReadWebApp"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/${var.webapp_prefix}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.app.arn]
    }
  }

  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*",
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

resource "aws_s3_bucket_policy" "data" {
  bucket     = aws_s3_bucket.data.id
  policy     = data.aws_iam_policy_document.data_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.data]
}
