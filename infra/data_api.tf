# データ API：API Gateway（HTTP API）＋ Lambda（FastAPI。コードは api/）。
# API Gateway が Cognito のアクセストークンを検証し、通ったリクエストだけを Lambda に渡す。

locals {
  data_api_name = "ct125-data-api"
  # Lambda の zip（api/scripts/build-lambda.ps1 が作る）。データ API とデバイス API の両方で使う
  data_api_zip = coalesce(var.data_api_zip, "${path.module}/../api/dist/lambda.zip")
}

# ---------------------------------------------------------------- Lambda

data "aws_iam_policy_document" "data_api_assume" {
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

resource "aws_iam_role" "data_api" {
  name               = "${local.data_api_name}-role"
  assume_role_policy = data.aws_iam_policy_document.data_api_assume.json
}

# ログを書く・データセットを読む、の 2 つだけ
data "aws_iam_policy_document" "data_api" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.data_api.arn}:*"]
  }
  statement {
    sid       = "ReadDatasets"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.data.arn}/${var.data_prefix}*"]
  }
}

resource "aws_iam_role_policy" "data_api" {
  name   = "${local.data_api_name}-policy"
  role   = aws_iam_role.data_api.id
  policy = data.aws_iam_policy_document.data_api.json
}

resource "aws_cloudwatch_log_group" "data_api" {
  name              = "/aws/lambda/${local.data_api_name}"
  retention_in_days = 14
}

resource "aws_lambda_function" "data_api" {
  function_name    = local.data_api_name
  role             = aws_iam_role.data_api.arn
  runtime          = "python3.13"
  architectures    = ["arm64"]
  handler          = "ct125_api.lambda_handler.handler"
  filename         = local.data_api_zip
  source_code_hash = filebase64sha256(local.data_api_zip)
  memory_size      = 512
  timeout          = 10

  environment {
    variables = {
      DATA_BUCKET = aws_s3_bucket.data.bucket
      DATA_PREFIX = var.data_prefix
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.data_api.name
  }

  depends_on = [aws_iam_role_policy.data_api]
}

# ---------------------------------------------------------------- API Gateway

resource "aws_apigatewayv2_api" "data" {
  name          = local.data_api_name
  protocol_type = "HTTP"
  # CloudFront と同じドメインから呼ぶので CORS は設定しない
}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.data.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = "https://${aws_cognito_user_pool.app.endpoint}"
    audience = [aws_cognito_user_pool_client.web.id]
  }
}

resource "aws_apigatewayv2_integration" "data_api" {
  api_id                 = aws_apigatewayv2_api.data.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.data_api.invoke_arn
  payload_format_version = "2.0"
}

# 動作確認用。ログイン不要
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.data.id
  route_key = "GET /api/health"
  target    = "integrations/${aws_apigatewayv2_integration.data_api.id}"
}

# それ以外の /api/* はすべてログインが必要
resource "aws_apigatewayv2_route" "authenticated" {
  api_id             = aws_apigatewayv2_api.data.id
  route_key          = "GET /api/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.data_api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_cloudwatch_log_group" "data_api_access" {
  name              = "/aws/apigateway/${local.data_api_name}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.data.id
  name        = "$default"
  auto_deploy = true

  # 想定外の大量アクセスで費用が増えないよう、秒あたりの上限を低めにする
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }

  # 機器からの受付（device_api.tf）は 1 台が数回呼ぶだけなので、さらに低くする
  route_settings {
    route_key              = local.device_route_key
    throttling_burst_limit = 5
    throttling_rate_limit  = 2
  }

  depends_on = [aws_apigatewayv2_route.device]

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.data_api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      time             = "$context.requestTime"
      method           = "$context.httpMethod"
      path             = "$context.path"
      status           = "$context.status"
      authError        = "$context.authorizer.error"
      user             = "$context.authorizer.claims.username"
      latencyMs        = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.data_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.data.execution_arn}/*/*"
}
