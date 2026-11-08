# デバイス API：ESP32 が生データを生データのバケット（buckets.tf の raw）に直接置くための受付（C）。
#   POST /api/device/uploads                    → 走行名とファイルごとの PUT 用 URL（15 分）
#   POST /api/device/uploads/{ride_id}/complete → 大きさを確かめて <走行>/upload_complete.json を置く（→ ct125-ride-pipeline）
# 認証は機器トークン（ハッシュは SSM の /ct125/devices/<機器ID>/token-sha256。pipeline/ の register-device で登録）。
# コードは画面用のデータ API と同じ zip（api/）。ハンドラーと権限だけが違う。

locals {
  device_api_name = "ct125-device-api"
  raw_prefix      = "" # 生データのバケットの直下に <走行>/ を置く
  raw_bucket      = aws_s3_bucket.role["raw"]
}

# ---------------------------------------------------------------- 権限：生データのバケットに置くことと、機器トークンのハッシュを読むことだけ

resource "aws_iam_role" "device_api" {
  name               = "${local.device_api_name}-role"
  assume_role_policy = data.aws_iam_policy_document.data_api_assume.json # 中身は同じ（Lambda が使う・このアカウントだけ）
}

data "aws_iam_policy_document" "device_api" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.device_api.arn}:*"]
  }
  # PUT 用 URL はこのロールの権限で署名する。機器はその URL のキーにしか置けない
  statement {
    sid       = "PutRawFiles"
    actions   = ["s3:PutObject"]
    resources = ["${local.raw_bucket.arn}/*"]
  }
  # 受け付けの記録を読む・置かれたファイルの大きさを確かめる（中身は返さない）
  statement {
    sid       = "CheckRawFiles"
    actions   = ["s3:GetObject"]
    resources = ["${local.raw_bucket.arn}/*"]
  }
  # 無いファイルを確かめたとき 403 ではなく 404 になるように
  statement {
    sid       = "ListRawFolder"
    actions   = ["s3:ListBucket"]
    resources = [local.raw_bucket.arn]
  }
  statement {
    sid       = "ReadDeviceTokenHashes"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/ct125/devices/*"]
  }
  statement {
    sid       = "DecryptDeviceTokenHashes"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "device_api" {
  name   = "${local.device_api_name}-policy"
  role   = aws_iam_role.device_api.id
  policy = data.aws_iam_policy_document.device_api.json
}

# ---------------------------------------------------------------- Lambda

resource "aws_cloudwatch_log_group" "device_api" {
  name              = "/aws/lambda/${local.device_api_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "device_api" {
  function_name    = local.device_api_name
  role             = aws_iam_role.device_api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "ct125_api.device_lambda_handler.handler"
  filename         = local.data_api_zip
  source_code_hash = filebase64sha256(local.data_api_zip)
  memory_size      = 256
  timeout          = 10

  environment {
    variables = {
      RAW_BUCKET                    = local.raw_bucket.bucket
      RAW_PREFIX                    = local.raw_prefix
      DEVICE_TOKEN_PARAMETER_PREFIX = "/ct125/devices/"
      UPLOAD_URL_SECONDS            = "900"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.device_api.name
  }

  depends_on = [aws_iam_role_policy.device_api]
}

# ---------------------------------------------------------------- API Gateway（画面用と同じ HTTP API に、POST のルートを足す）

resource "aws_apigatewayv2_integration" "device_api" {
  api_id                 = aws_apigatewayv2_api.data.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.device_api.invoke_arn
  payload_format_version = "2.0"
}

# JWT（人のログイン）ではなく、機器トークンを Lambda の中で確かめる
resource "aws_apigatewayv2_route" "device" {
  api_id    = aws_apigatewayv2_api.data.id
  route_key = local.device_route_key
  target    = "integrations/${aws_apigatewayv2_integration.device_api.id}"
}

locals {
  device_route_key = "POST /api/device/{proxy+}"
}

resource "aws_lambda_permission" "api_gateway_device" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.device_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.data.execution_arn}/*/*"
}
