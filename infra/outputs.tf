output "bucket_name" {
  description = "pipeline/ の config/local.yaml の aws.bucket に書く"
  value       = aws_s3_bucket.data.bucket
}

output "bucket_region" {
  value = var.aws_region
}

output "aws_profile" {
  value = var.aws_profile
}

output "app_url" {
  value = "https://${var.app_domain}/"
}

output "cloudfront_domain" {
  description = "Cloudflare で <app_domain> の CNAME の向き先にする（プロキシはオフ）"
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
