# 走行データの処理：生データのバケットに <走行>/upload_complete.json が置かれたら、Lambda（コンテナ）が
#   前処理 → 分類 → 学習済みモデルで点数付け → 画面用データの書き出し → 作業用に保存 → 台帳 → 公開用へ
# を行う。手動で {"action": "retrain"}（全走行で学習し直す）・{"action": "publish", "run_id": ...}（公開）を渡せる。
# コードは pipeline/src/ct125/（flow.py と cloud/）、イメージは pipeline/scripts/build-pipeline-image.ps1 で作る。
#
# 初回だけ：ECR を先に作る → イメージを上げる → 全体を apply
#   terraform apply -target=aws_ecr_repository.pipeline
#   （pipeline/ で）./scripts/build-pipeline-image.ps1
#   terraform apply

locals {
  pipeline_name = "ct125-ride-pipeline"
}

# ---------------------------------------------------------------- ECR（コンテナの置き場所）

resource "aws_ecr_repository" "pipeline" {
  name                 = local.pipeline_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true # イメージは作り直せるので、destroy で一緒に消してよい

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 古いイメージは 5 個まで残す
resource "aws_ecr_lifecycle_policy" "pipeline" {
  repository = aws_ecr_repository.pipeline.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 5 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 5 }
      action       = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------- 権限

data "aws_iam_policy_document" "pipeline_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  name               = "${local.pipeline_name}-role"
  assume_role_policy = data.aws_iam_policy_document.pipeline_assume.json
}

locals {
  raw_arn    = aws_s3_bucket.role["raw"].arn
  work_arn   = aws_s3_bucket.role["work"].arn
  public_arn = aws_s3_bucket.role["public"].arn
}

# 処理の Lambda：生データを読み、作業用に読み書きし、公開用に書く（公開の仕組みはこの Lambda の中だけ）
data "aws_iam_policy_document" "pipeline" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.pipeline.arn}:*"]
  }
  statement {
    sid       = "ReadRaw"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_arn}/*"]
  }
  statement {
    sid       = "ReadWriteWork"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${local.work_arn}/*"]
  }
  statement {
    sid       = "PublishPublic"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.public_arn}/*"]
  }
  # 一覧を取る（走行の一覧・モデルの版・処理の結果）。無いファイルを読んだとき 403 ではなく 404 になるようにも要る
  statement {
    sid       = "ListBuckets"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_arn, local.work_arn, local.public_arn]
  }
}

resource "aws_iam_role_policy" "pipeline" {
  name   = "${local.pipeline_name}-policy"
  role   = aws_iam_role.pipeline.id
  policy = data.aws_iam_policy_document.pipeline.json
}

# ---------------------------------------------------------------- Lambda

resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/aws/lambda/${local.pipeline_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "pipeline" {
  function_name = local.pipeline_name
  role          = aws_iam_role.pipeline.arn
  package_type  = "Image"
  image_uri     = var.pipeline_image_uri
  architectures = ["x86_64"] # Windows の Docker でそのまま作れる形
  memory_size   = 3008
  timeout       = 900 # 学習し直し（全走行）でも収まる上限

  ephemeral_storage {
    size = 2048 # 生データ（1 走行 十数 MB）と中間ファイルを /tmp に置く
  }

  environment {
    variables = {
      RAW_BUCKET    = aws_s3_bucket.role["raw"].bucket
      RAW_PREFIX    = ""
      WORK_BUCKET   = aws_s3_bucket.role["work"].bucket
      WORK_PREFIX   = ""
      PUBLIC_BUCKET = aws_s3_bucket.role["public"].bucket
      PUBLIC_PREFIX = "${local.public_dataset_prefix}shared/"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.pipeline.name
  }

  lifecycle {
    precondition {
      condition     = var.pipeline_image_uri != null
      error_message = "pipeline_image_uri がありません。先に pipeline/ の scripts/build-pipeline-image.ps1 でイメージを上げてください。"
    }
  }

  depends_on = [aws_iam_role_policy.pipeline]
}

# S3 からの呼び出しは非同期。失敗したら 1 回だけやり直す（処理は何度やっても同じ結果になる）
resource "aws_lambda_function_event_invoke_config" "pipeline" {
  function_name                = aws_lambda_function.pipeline.function_name
  maximum_retry_attempts       = 1
  maximum_event_age_in_seconds = 3600
}

# ---------------------------------------------------------------- S3 のイベント

resource "aws_lambda_permission" "s3_invoke_pipeline" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.pipeline.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.role["raw"].arn
  source_account = data.aws_caller_identity.current.account_id
}

# 注意：このバケットの通知設定はこのリソースだけで管理する（ほかで足すと上書きし合う）
resource "aws_s3_bucket_notification" "raw_upload_complete" {
  bucket = aws_s3_bucket.role["raw"].id

  lambda_function {
    lambda_function_arn = aws_lambda_function.pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = "/upload_complete.json"
  }

  depends_on = [aws_lambda_permission.s3_invoke_pipeline]
}
