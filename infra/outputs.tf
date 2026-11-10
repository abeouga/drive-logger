output "bucket_name" {
  description = "画面（React のビルド結果 webapp/）のバケット。作り直しの前は走行データもここにあった"
  value       = aws_s3_bucket.data.bucket
}

output "raw_bucket_name" {
  description = "生データのバケット（デバイス API が書き、処理が読む）"
  value       = aws_s3_bucket.role["raw"].bucket
}

output "work_bucket_name" {
  description = "作業用のバケット（処理の結果と記録・モデル・走行の台帳）"
  value       = aws_s3_bucket.role["work"].bucket
}

output "public_bucket_name" {
  description = "公開用のバケット（画面が読む datasets/shared/。書けるのは処理の Lambda だけ）"
  value       = aws_s3_bucket.role["public"].bucket
}

output "local_pipeline_role_arn" {
  description = "PC の処理に使うロール（~/.aws/config の ct125-local-pipeline プロファイルの role_arn）"
  value       = aws_iam_role.local_pipeline.arn
}

output "env" {
  description = "環境の名前（prod か test）。スクリプトが向き先を確かめるのに使う"
  value       = var.env
}

output "device_token_parameter_prefix" {
  description = "機器トークンのハッシュを置く SSM の場所（pipeline の register-device が書く）"
  value       = local.device_parameter_prefix
}

output "bucket_region" {
  value = var.aws_region
}

output "aws_profile" {
  value = var.aws_profile
}

output "app_url" {
  value = "https://${local.app_domain}/"
}

output "cloudfront_domain" {
  description = "Cloudflare で画面のドメイン（app_url）の CNAME の向き先にする（プロキシはオフ）"
  value       = aws_cloudfront_distribution.app.domain_name
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.app.id
}

output "webapp_s3_uri" {
  description = "React のビルド結果を置く場所（web/scripts/deploy.ps1）"
  value       = "s3://${aws_s3_bucket.data.bucket}/${var.webapp_prefix}/"
}

output "auth_authority" {
  description = "OIDC の発行元（フロントの VITE_AUTH_AUTHORITY）"
  value       = "https://${aws_cognito_user_pool.app.endpoint}"
}

output "auth_client_id" {
  description = "フロントの VITE_AUTH_CLIENT_ID（秘密ではない）"
  value       = aws_cognito_user_pool_client.web.id
}

output "auth_domain" {
  description = "ログイン画面のドメイン（フロントの VITE_AUTH_DOMAIN。ログアウトで使う）"
  value       = "https://${aws_cognito_user_pool_domain.app.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "user_pool_id" {
  value = aws_cognito_user_pool.app.id
}

output "pipeline_repository_url" {
  description = "走行データ処理のコンテナを上げる ECR（pipeline/ の scripts/build-pipeline-image.ps1 が使う）"
  value       = aws_ecr_repository.pipeline.repository_url
}

output "data_api_function_name" {
  value = aws_lambda_function.data_api.function_name
}

output "pipeline_function_name" {
  description = "走行データ処理の Lambda。学習し直すときは {\"action\": \"retrain\"} で呼ぶ"
  value       = aws_lambda_function.pipeline.function_name
}

output "certificate_validation_record" {
  description = "Cloudflare に足す CNAME（プロキシはオフ＝DNS のみ）"
  value = [for o in aws_acm_certificate.app.domain_validation_options : {
    name  = o.resource_record_name
    type  = o.resource_record_type
    value = o.resource_record_value
  }]
}
