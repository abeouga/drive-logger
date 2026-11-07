# 走行データの処理：S3 の raw/<走行>/upload_complete.json が置かれたら、Lambda（コンテナ）が
#   前処理 → 学習済みモデルで点数付け → 画面用データの書き出し → app/v1/datasets/shared/ へ
# を行う。手動で {"action": "retrain"} を渡すと、全走行で学習し直す。
# コードは pipeline/src/ct125/cloud/、イメージは pipeline/scripts/build-pipeline-image.ps1 で作る。
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
  bucket_arn = aws_s3_bucket.data.arn
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.pipeline.arn}:*"]
  }
  statement {
    sid     = "ReadInputs"
    actions = ["s3:GetObject"]
    resources = [
      "${local.bucket_arn}/raw/*",
      "${local.bucket_arn}/models/*",
      "${local.bucket_arn}/${var.data_prefix}*",
    ]
  }
  statement {
    sid     = "WriteOutputs"
    actions = ["s3:PutObject"]
    resources = [
      "${local.bucket_arn}/processed/*",
      "${local.bucket_arn}/models/*",
      "${local.bucket_arn}/${var.data_prefix}*",
    ]
  }
  # 一覧を取る（raw/ の走行一覧）。無いファイルを読んだとき 403 ではなく 404 になるよう、読む場所にも付ける
  statement {
    sid       = "ListInputFolders"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["raw/*", "models/*", "${var.data_prefix}*"]
    }
  }
  statement {
    sid       = "ReadPrivatePoints"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${var.private_points_parameter}"]
  }
  statement {
    sid       = "DecryptPrivatePoints"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
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
      DATA_BUCKET              = aws_s3_bucket.data.bucket
      RAW_PREFIX               = "raw/"
      PROCESSED_PREFIX         = "processed/"
      MODELS_PREFIX            = "models/"
      APP_PREFIX               = "${var.data_prefix}shared/"
      PRIVATE_POINTS_PARAMETER = var.private_points_parameter
      WORK_DIR                 = "/tmp/ct125"
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
  source_arn     = aws_s3_bucket.data.arn
  source_account = data.aws_caller_identity.current.account_id
}

# 注意：このバケットの通知設定はこのリソースだけで管理する（ほかで足すと上書きし合う）
resource "aws_s3_bucket_notification" "raw_upload_complete" {
  bucket = aws_s3_bucket.data.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "raw/"
    filter_suffix       = "/upload_complete.json"
  }

  depends_on = [aws_lambda_permission.s3_invoke_pipeline]
}
